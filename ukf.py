"""
无迹卡尔曼滤波 (UKF) 估计器
支持三种模型:
  传统一阶RC:  x = [SOC, V1]                                  (n=2)
  改进模型:    x = [SOC, V1, V_sd]                             (n=3)
  自适应模型:  x = [SOC, V1, V_sd, tau_sd]  — τ_sd 在线估计   (n=4)

观测方程: V_terminal = OCV(SOC) - V1 - V_sd - I*R0
"""

import numpy as np
from parameters import Q_n, R0, R1, C1, tau_sd, K_sd, ocv_soc_poly


class UKFEstimator:

    def __init__(self, model_type='traditional', Q=None, R=None):
        self.model_type = model_type

        n_map = {'traditional': 2, 'improved': 3, 'adaptive': 4}
        self.n = n_map[model_type]

        if Q is None:
            if model_type == 'traditional':
                Q = np.diag([1e-8, 1e-6])
            elif model_type == 'improved':
                Q = np.diag([1e-8, 1e-6, 1e-6])
            else:  # adaptive
                Q = np.diag([1e-8, 1e-6, 1e-6, 0.5])  # τ_sd 随机游走

        self.Q = Q
        self.R = R if R is not None else np.array([[1e-5]])

        # UKF 超参数 (kappa=0 避免小状态维数下 n+λ≈0 的退化)
        self.alpha = 1.0
        self.beta = 2.0
        self.kappa = 0.0
        self.lam = self.alpha**2 * (self.n + self.kappa) - self.n

        # 权重
        n = self.n
        self.Wm = np.full(2 * n + 1, 0.5 / (n + self.lam))
        self.Wc = np.full(2 * n + 1, 0.5 / (n + self.lam))
        self.Wm[0] = self.lam / (n + self.lam)
        self.Wc[0] = self.lam / (n + self.lam) + (1 - self.alpha**2 + self.beta)

    # ---------- sigma 点生成 ----------
    def _sigma_points(self, x, P):
        n = self.n
        x = np.asarray(x).reshape(n)
        L = np.linalg.cholesky((n + self.lam) * P)
        X = np.zeros((n, 2 * n + 1))
        X[:, 0] = x
        X[:, 1:n + 1]     = x[:, None] + L
        X[:, n + 1:2 * n + 1] = x[:, None] - L
        return X

    # ---------- 状态转移 ----------
    def _f(self, x, I, dt):
        SOC, V1 = x[0], x[1]
        SOC_n = SOC - dt * I / Q_n
        SOC_n = max(0.0, min(1.0, SOC_n))

        exp1 = np.exp(-dt / (R1 * C1))
        V1_n = V1 * exp1 + I * R1 * (1 - exp1)

        if self.model_type == 'traditional':
            return np.array([SOC_n, V1_n])

        V_sd = x[2]

        if self.model_type == 'improved':
            tsd = tau_sd  # 固定值
        else:  # adaptive — 用当前估计的 τ_sd
            tsd = max(10.0, min(2000.0, x[3]))

        exp_sd = np.exp(-dt / tsd)
        V_sd_n = V_sd * exp_sd + I * K_sd * (1 - exp_sd)

        if self.model_type == 'improved':
            return np.array([SOC_n, V1_n, V_sd_n])
        else:
            return np.array([SOC_n, V1_n, V_sd_n, x[3]])  # τ_sd 随机游走

    # ---------- 观测方程 ----------
    def _h(self, x, I):
        Vt = ocv_soc_poly(x[0]) - x[1] - I * R0
        if self.model_type != 'traditional':
            Vt -= x[2]  # V_sd 修正
        return np.array([Vt])

    # ---------- UKF 预测 ----------
    def predict(self, x, P, I, dt):
        n = self.n
        X = self._sigma_points(x, P)

        Xp = np.zeros((n, 2 * n + 1))
        for i in range(2 * n + 1):
            Xp[:, i] = self._f(X[:, i], I, dt)

        xp = Xp @ self.Wm

        Pp = self.Q.copy()
        for i in range(2 * n + 1):
            d = (Xp[:, i] - xp).reshape(-1, 1)
            Pp += self.Wc[i] * (d @ d.T)

        self._Xp = Xp
        self._xp = xp
        self._Pp = Pp
        return xp, Pp

    # ---------- UKF 更新 ----------
    def update(self, xp, Pp, I, V_meas):
        n = self.n
        Xp = self._Xp

        Z = np.zeros((1, 2 * n + 1))
        for i in range(2 * n + 1):
            Z[:, i] = self._h(Xp[:, i], I)

        zp = Z @ self.Wm

        S = self.R.copy()
        for i in range(2 * n + 1):
            d = (Z[:, i] - zp).reshape(-1, 1)
            S += self.Wc[i] * (d @ d.T)

        Pxz = np.zeros((n, 1))
        for i in range(2 * n + 1):
            dx = (Xp[:, i] - xp).reshape(-1, 1)
            dz = (Z[:, i] - zp).reshape(-1, 1)
            Pxz += self.Wc[i] * (dx @ dz.T)

        K = Pxz @ np.linalg.inv(S)

        innovation = V_meas - zp.item()
        xu = xp + (K * innovation).flatten()
        xu[0] = max(0.0, min(1.0, xu[0]))

        if self.model_type != 'traditional':
            xu[2] = max(-0.5, xu[2])           # V_sd 下限保护

        if self.model_type == 'adaptive':
            xu[3] = max(10.0, min(2000.0, xu[3]))  # τ_sd ∈ [10, 2000]s

        Pu = Pp - K @ S @ K.T
        Pu = (Pu + Pu.T) / 2

        return xu, Pu

    # ---------- 单步 ----------
    def step(self, x, P, I_pred, I_upd, V_meas, dt):
        xp, Pp = self.predict(x, P, I_pred, dt)
        xu, Pu = self.update(xp, Pp, I_upd, V_meas)
        return xu, Pu
