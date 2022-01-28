from mrmustard.lab import Vacuum, Gaussian
from mrmustard.lab import Dgate, Sgate, Rgate, Attenuator  # 1-mode gates ; parallelizable
from mrmustard.lab import BSgate, MZgate, S2gate  # 2-mode gates
from mrmustard.lab import Ggate, Interferometer  # N-mode gates
import matplotlib.pyplot as plt  
import time


shotsUsed = []
outputs = []
timesTaken = []
for i in range(0, 7):
	shotsNeeded = 10**i
	for i in range(0, shotsNeeded):
		t0 = time.time()
		G1 = Gaussian(num_modes=4)
		t1 = time.time()
		shotsUsed.append(shotsNeeded)
		timesTaken.append(t1-t0)
	outputs.append(G1.fock)
plt.plot(shotsUsed, timesTaken)
plt.title("Time Taken for Various Shot Numbers of Randomized GBS on Nvidia MX150 with Mr. Mustard")
plt.xlabel("Shots Used")
plt.ylabel("Time (s)")
plt.savefig("shotsbenchmark_mrmustard_nvidiamx150.png", bbox_inches='tight')
print(outputs)
print("Time taken in seconds: ", (t1 - t0))
