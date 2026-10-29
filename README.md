# qff_bits_sardines · Quantum Fingerprint

**IBM Qiskit Fall Fest 2026, BITS Pilani K.K. Birla Goa Campus**
Beginner track · Problem 5: *Quantum Fingerprint: creative integrity and tamper detection*
Team **sardines** · team code `TEAM-P6GK23`

> Work in progress. The hackathon runs from 29 Oct 2026, 00:00 to 31 Oct 2026, 23:59 IST. This README becomes the
> submission README.

## Team

| Name | GitHub | Owns |
|---|---|---|
| Rashida Baldiwala (team leader) |  | [@rsb17](https://github.com/rsb17) | tampering experiments, write-up, demo |
| Ansh Varma |  | [@aviate15](https://github.com/aviate15) | app and user experience |
| Darshan Rajagoli |  | [@darshanrajagoli](https://github.com/darshanrajagoli) | quantum core |

## The idea

Can a quantum experiment tell you whether a piece of digital art has been changed?

We build the construction this problem is named after: **quantum fingerprinting** (Buhrman, Cleve, Watrous and
de Wolf, 2001).

1. **Encode.** The image's bits go through an error-correcting code. The codeword sets the signs of the amplitudes of a
   q-qubit state, |h_x⟩ = (1/√m) Σᵢ (−1)^E(x)ᵢ |i⟩ with m = 2^q. The code spreads any change across the whole codeword,
   so two different images give states with a small, provably bounded overlap, even when they differ by one pixel.
2. **Compare.** A SWAP test on two fingerprints (one ancilla, a Hadamard, controlled-SWAPs, a Hadamard) reads 0 with
   probability ½ + ½|⟨h_x|h_y⟩|². Identical images always read 0. Every 1 is evidence of tampering, and the code
   distance fixes how many shots it takes to catch an edit at a chosen confidence.
3. **Show it.** A web app: drop in an artwork, see its fingerprint, edit the image, and watch the SWAP test catch the
   edit shot by shot. Fingerprints of image tiles show *where* it changed.

What we do not claim: this is not a secure signature or watermark. Simulating it on a classical computer gives no
advantage over SHA-256. The 2001 advantage (O(log n) qubits against Θ(√n) classical bits) holds in the
simultaneous-message model without shared randomness. We measure collisions, shot noise and hardware noise and report
them.

## Judging map

Each criterion of Problem 5, and where this repository answers it.

| Criterion (points) | Where |
|---|---|
| Design of the quantum fingerprinting approach (30) | *to come* |
| Tampering experiment and evaluation (25) | *to come* |
| Understanding of encoding and measurement (20) | *to come* |
| Creativity and usability (15) | *to come* |
| Limitations and clarity (10) | *to come* |

## Setup and run

*To come.*

## Work done before the hackathon

None. Everything in this repository was written during the hackathon, from 29 Oct 2026 onwards. Third-party libraries,
data and images are listed here as they are added.

## References

- H. Buhrman, R. Cleve, J. Watrous, R. de Wolf. Quantum fingerprinting. *Phys. Rev. Lett.* 87, 167902 (2001).
  [arXiv:quant-ph/0102001](https://arxiv.org/abs/quant-ph/0102001)
- J. C. Garcia-Escartin, P. Chamorro-Posada. SWAP test and Hong-Ou-Mandel effect are equivalent. *Phys. Rev. A* 87,
  052330 (2013). (The destructive SWAP test, which needs no ancilla.)
