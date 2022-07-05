"""
Using a Hidden Markov Model with Poisson Emissions to Understand Earthquakes
----------------------------------------------------------------------------
Let's look at data of magnitude 7+ earthquakes between 1900-2006 in the
world collected by the US Geological Survey as described in this textbook:
Zucchini & MacDonald, "Hidden Markov Models for Time Series"
(https://ayorho.files.wordpress.com/2011/05/chapter1.pdf). The goal is to
see if we can separate out different tectonic processes that cause
earthquakes based on their frequency of occurance. The idea is that each
tectonic boundary may cause earthquakes with a particular distribution
of waiting times depending on how active it is. This might tell help us
predict future earthquake danger, espeically on a geological time scale.

Based on
https://github.com/hmmlearn/hmmlearn/blob/main/examples/plot_poisson_hmm.py
"""

import jax.numpy as jnp
import jax.random as jr
import matplotlib.pyplot as plt
from scipy.stats import poisson
from ssm_jax.hmm.learning import hmm_fit_em
from ssm_jax.hmm.models.poisson_hmm import PoissonHMM

# earthquake data from http://earthquake.usgs.gov/
earthquakes = jnp.array([
    13, 14, 8, 10, 16, 26, 32, 27, 18, 32, 36, 24, 22, 23, 22, 18, 25, 21, 21, 14, 8, 11, 14, 23, 18, 17, 19, 20, 22,
    19, 13, 26, 13, 14, 22, 24, 21, 22, 26, 21, 23, 24, 27, 41, 31, 27, 35, 26, 28, 36, 39, 21, 17, 22, 17, 19, 15, 34,
    10, 15, 22, 18, 15, 20, 15, 22, 19, 16, 30, 27, 29, 23, 20, 16, 21, 21, 25, 16, 18, 15, 18, 14, 10, 15, 8, 15, 6,
    11, 8, 7, 18, 16, 13, 12, 13, 20, 15, 16, 12, 18, 15, 16, 13, 15, 16, 11, 11
])

# Plot the sampled data
fig, ax = plt.subplots()
ax.plot(earthquakes, ".-", ms=6, mfc="orange", alpha=0.7)
ax.set_xticks(range(0, earthquakes.size, 10))
ax.set_xticklabels(range(1906, 2007, 10))
ax.set_xlabel('Year')
ax.set_ylabel('Count')
fig.show()

emission_dim = earthquakes.size

# %%
# Now, fit a Poisson Hidden Markov Model to the data.
scores = list()
models = list()

for num_states in range(1, 5):
    for idx in range(10):  # ten different random starting states

        key = jr.PRNGKey(idx)
        model = PoissonHMM.random_initialization(key, num_states, emission_dim)
        model, _ = hmm_fit_em(model, earthquakes[:, None])
        models.append(model)
        scores.append(model.marginal_log_prob(earthquakes[:, None]))
        print(f'Score: {scores[-1]}')

# get the best model
model = models[jnp.argmax(scores)]
print(f'The best model had a score of {max(scores)} and '
      f'{model.num_states} components')
