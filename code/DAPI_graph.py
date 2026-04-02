import numpy as np
import matplotlib.pyplot as plt

# Trust Score range starting at 0
trust_scores = np.linspace(0, 1, 100)

# Fixed gamma
gamma = 0.5

# Beta values and green shades
beta_values = [1.0, 2.0, 3.0]
colors = ['lightgreen', 'mediumseagreen', 'darkgreen']

# Plot
plt.figure(figsize=(8, 6))

for beta, color in zip(beta_values, colors):
    epsilon = beta * np.power(trust_scores, gamma)  # ε = β * Ti^γ
    plt.plot(trust_scores, epsilon, label=f'β = {beta}, γ = {gamma}', linewidth=2, color=color)

# Graph configuration
plt.xlabel('Trust Score $T_i$', fontsize=12)
plt.ylabel('Privacy Budget $\\varepsilon_i$', fontsize=12)
plt.title('DAPI: Privacy Budget vs. Trust Score', fontsize=14)
plt.legend(title='Parameter Settings')
plt.grid(True)
plt.xlim(0, 1)
plt.ylim(0, max(beta_values))  # Adjust y-axis based on max β
plt.tight_layout()
plt.show()
