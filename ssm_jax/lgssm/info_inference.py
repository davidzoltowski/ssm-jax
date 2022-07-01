import jax.numpy as jnp
import jax.random as jr
from jax import lax
from distrax import MultivariateNormalFullCovariance as MVN
import chex

@chex.dataclass
class LGSSMInfoParams:
    """Lightweight container for LGSSM parameters in information form.
    """
    initial_mean: chex.Array
    initial_precision: chex.Array
    dynamics_matrix: chex.Array
    dynamics_precision: chex.Array
    dynamics_input_weights: chex.Array
    dynamics_bias: chex.Array
    emission_matrix: chex.Array
    emission_input_weights: chex.Array
    emission_bias: chex.Array
    emission_precision: chex.Array


@chex.dataclass
class LGSSMInfoPosterior:
    """Simple wrapper for properties of an LGSSM posterior distribution in
    information form.

    Attributes:
            filtered_means: (T,K) array,
                E[x_t | y_{1:t}, u_{1:t}].
            filtered_precisions: (T,K,K) array,
                inv(Cov[x_t | y_{1:t}, u_{1:t}]).
    """
    filtered_etas: chex.Array = None
    filtered_precisions: chex.Array = None


# Helper functions
_get_params = lambda x, dim, t: x[t] if x.ndim == dim+1 else x


def _info_predict(eta, Lambda, F, Q_prec, B, u, b):
    """Predict next mean and precision under a linear Gaussian model

    Marginalising over the uncertainty in z_t the predicted latent state at
    the next time step is given by:
        p(z_{t+1}| z_t, u_t) 
            = \int p(z_{t+1}, z_t | u_t) dz_t
            = \int N(z_t | mu_t, Sigma_t) N(z_{t+1} | F z_t + B u_t + b, Q) dz_t
            = N(z_t | m_{t+1|t}, Sigma_{t+1|t})
    with
        m_{t+1|t} = F m_t + B u_t + b
        Sigma_{t+1|t} = F Sigma_t F^T + Q

    The corresponding information form parameters are:
        eta_{t+1|t} = K eta_t + Lambda_{t+1|t} (B u_t + b)
        Lambda_{t+1|t} = L Q_prec L^T + K Lambda_t K^T
    where
        K = Q_prec F ( Lambda_t + F^T Q_prec F)^{-1}
        L = I - K F^T

    Args:
        eta (D_hid,): prior precision weighted mean.
        Lambda (D_hid,D_hid): prior precision matrix.
        F (D_hid,D_hid): dynamics matrix.
        Q_prec (D_hid,D_hid): dynamics precision matrix.
        B (D_hid,D_in): dynamics input matrix.
        u (D_in,): inputs.
        b (D_hid,): dynamics bias.

    Returns:
        eta_pred (D_hid,): predicted precision weighted mean.
        Lambda_pred (D_hid,D_hid): predicted precision.
    """
    K = jnp.linalg.solve(Lambda + F.T @ Q_prec @ F, F.T @ Q_prec).T
    I = jnp.eye(len(Lambda))
    ## This version should be more stable than:
    # Lambda_pred = (I - K @ F.T) @ Q_prec
    ImKF = I - K @ F.T
    Lambda_pred = ImKF @ Q_prec @ ImKF.T + K @ Lambda @ K.T
    eta_pred = K @ eta + Lambda_pred @ (B @ u + b)
    return eta_pred, Lambda_pred


def _info_condition_on(eta, Lambda, H, R_prec, D, u, d, obs):
    """Condition a Gaussian potential on a new linear Gaussian observation.

        p(z_t|y_t, u_t) \prop  N(z_t | mu_{t|t-1}, Sigma_{t|t-1}) * 
                          N(y_t | H z_t + D u_t + d, R)

    The prior precision and precision-weighted mean are given by:
        Lambda_{t|t-1} = Sigma_{t|t-1}^{-1}
        eta_{t|t-1} = Lambda{t|t-1} mu_{t|t-1},
    respectively. 

    The upated parameters are then:
        Lambda_t = Lambda_{t|t-1} + H^T R_prec H
        eta_t = eta_{t|t-1} + H^T R_prec (y_t - Du - d)

    Args:
        eta (D_hid,): prior precision weighted mean.
        Lambda (D_hid,D_hid): prior precision matrix.
        H (D_obs,D_hid): emission matrix.
        R_prec (D_obs,D_obs): precision matrix for observations.
        D (D_obs,D_in): emission input weights.
        u (D_in,): inputs.
        d (D_obs,): emission bias.
        obs (D_obs,): observation.

    Returns:
        eta_cond (D_hid,): posterior precision weighted mean.
        Lambda_cond (D_hid,D_hid): posterior precision.
    """
    HR = H.T @ R_prec
    Lambda_cond = Lambda + HR @ H
    eta_cond = eta + HR @ (obs - D @ u - d)
    return eta_cond, Lambda_cond


def lgssm_info_filter(params, emissions, inputs):
    """Run a Kalman filter to produce the filtered state estimates.

    Args:
        params: an LGSSMInfoParams instance.
        emissions (T,D_obs): array of observations.
        inputs (T,D_in): array of inputs.

    Returns:
        filtered_posterior: LGSSMInfoPosterior instance containing,
            filtered_etas
            filtered_precisions
    """
    num_timesteps = len(emissions) 

    def _step(carry, t):
        pred_eta, pred_prec = carry

        # Shorthand: get parameters and inputs for time index t
        F = _get_params(params.dynamics_matrix, 2, t)
        Q_prec = _get_params(params.dynamics_precision, 2, t)
        H = _get_params(params.emission_matrix, 2, t)
        R_prec = _get_params(params.emission_precision, 2, t)
        B = _get_params(params.dynamics_input_weights, 2, t)
        b = _get_params(params.dynamics_bias, 1, t)
        D = _get_params(params.emission_input_weights, 2, t)
        d = _get_params(params.emission_bias, 1, t)
        u = inputs[t]
        y = emissions[t]

        # Condition on this emission
        filtered_eta, filtered_prec = _info_condition_on(
            pred_eta, pred_prec, H, R_prec, D, u, d, y)

        # Predict the next state
        pred_mean, pred_cov = _info_predict(
            filtered_eta, filtered_prec, F, Q_prec, B, u, b)

        return (pred_mean, pred_cov), (filtered_eta, filtered_prec)

    # Run the Kalman filter
    initial_eta = params.initial_precision @ params.initial_mean 
    carry = (initial_eta, params.initial_precision)
    _, (filtered_etas, filtered_precisions) = lax.scan(
        _step, carry, jnp.arange(num_timesteps))
    return LGSSMInfoPosterior(filtered_etas=filtered_etas,
                              filtered_precisions=filtered_precisions)


