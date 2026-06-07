# Methodological risk register for publication review

This register turns the paper's strongest claims into explicit, reviewable risk items. It is intended for authors, internal reviewers, and journal reviewers who need to distinguish validated evidence from screening assumptions.

Current date of this register: 2026-06-07.

## Central falsifiable claim

For clustered, synchronized, DC-native AI factories, moving the AC/DC boundary from each campus to a utility-operated subtransmission DC backbone should jointly:

1. reduce corridor-plus-conversion losses relative to a traditional AC corridor under the stated voltage, distance, power-factor, and converter-efficiency assumptions;
2. centralize AC harmonic ownership at one grid-facing terminal rather than leaving several campus converters as independent AC-facing harmonic sources;
3. reduce 0.1-20 Hz grid-side power modulation and the associated PCC voltage-deviation proxy relative to architectures that pass more synchronized training dynamics into the AC corridor.

The manuscript should not claim that a specific hardware design is complete, that IEEE 519 compliance is guaranteed, or that every AI data center should use subtransmission DC.

## Evidence ladder

| Claim layer | Evidence currently in repository | Remaining publication risk | Required phrasing |
|---|---|---|---|
| Architecture comparison | Three architectures are implemented with the same useful 800 VDC load boundary; figure provenance and reproduction docs are present. | Reviewers may ask whether the selected boundary unfairly advantages DC. | State that the comparison is intentionally made at the useful 800 VDC interface because future AI-rack roadmaps are DC-native. |
| Efficiency | Reference case, load-distance sweep, Monte Carlo uncertainty, and one-at-a-time sensitivity are archived. | Local SST at 99.0% efficiency can beat the DC backbone on efficiency alone. | Treat efficiency as one component of a multi-objective result; explicitly preserve the high-efficiency-SST counter-case. |
| Harmonics | Internal frequency-domain screening, harmonic robustness sweep, OpenDSS-compatible files, and archived direct OpenDSS runs are provided. | Spectra, damping, network impedance, and phase coherence are screening assumptions, not site studies. | Use “screening metric,” “planning guide,” and “ownership boundary”; avoid “compliance guarantee.” |
| Dynamics | Averaged EMT-style first-order command model, time-step convergence, transfer-function check, reference waveform, and 3,072-case robustness grid are archived. | Synthetic load waveform and first-order command model are not a switching EMT or hardware-in-the-loop validation. | Use “architecture-level exposure comparison”; identify HIL and pilot-grade EMT as follow-up work. |
| DC protection | Fault/protection screening waveforms are included. | DC breaker, grounding, insulation coordination, and relay selectivity are not designed. | Use “protection-zone screening” only; do not imply deployable relay design. |
| Cost/copper | Annual value and current-length proxy are archived. | No capex, right-of-way, substation, equipment, reliability, or lifecycle cost model. | Call it a first-order envelope, not a business case. |
| Public planning context | Public CAISO/San Jose load-pocket and HVDC planning references are listed in the manuscript generator. | A public precedent does not validate the proposed architecture. | Use only as motivation for scale and planning relevance. |

## High-priority reviewer attack surface

### R1. “The harmonic model is too synthetic.”

**Risk.** The current screening spectra and resonance factors are transparent but stylized. Reviewers in power quality may require stronger justification.

**Mitigation already present.** The repository includes a harmonic robustness grid, p95 individual harmonic tables, OpenDSS-compatible files, direct OpenDSS Monte Carlo outputs, and a run log.

**Next best improvement.** Add a supplementary sensitivity that varies harmonic current spectra independently of architecture so that the result is shown as an ownership/number-of-interfaces result rather than a hidden spectral-assumption result. Report the boundary where distributed AC plus filtering equals the DC terminal case.

**Manuscript guardrail.** State that project-specific IEEE 519 studies remain mandatory.

### R2. “The dynamic waveform is synthetic.”

**Risk.** The waveform is parameterized from published AI-training power behavior but is not a released measured trace.

**Mitigation already present.** The repository includes a dynamic robustness grid over campus count, power scale, voltage class, short-circuit ratio, coherence, and corridor length, plus transfer-function and time-step checks.

**Next best improvement.** Add a second family of waveforms with randomized duty cycle, communication interval, dip duration, and checkpoint period; then report whether the rank ordering of architectures is unchanged.

**Manuscript guardrail.** Make the claim about architectural filtering of coherent load modulation, not about a universal AI workload trace.

### R3. “The efficiency advantage is not robust against local SST assumptions.”

**Risk.** The archived reference table already shows the 99.0% local-SST sensitivity can outperform the DC backbone on losses.

**Mitigation already present.** The repository keeps the counter-case instead of hiding it.

**Next best improvement.** In the main text, move the high-efficiency SST result closer to the first efficiency claim and frame the paper as a multi-objective architecture result.

**Manuscript guardrail.** Do not use efficiency alone as the novelty claim.

### R4. “Subtransmission DC protection is underdeveloped.”

**Risk.** DC protection is a major deployment blocker for MVDC/HVDC systems.

**Mitigation already present.** The supplementary protection screening exposes detection, current limiting, section isolation, and healthy-campus ride-through functions.

**Next best improvement.** Add a protection requirements table: maximum allowed detection time, breaker opening time, current-limiting target, grounding assumption, temporary overvoltage issue, and insulation-coordination item.

**Manuscript guardrail.** Say the paper proposes a planning architecture and screening model, not a protection product.

### R5. “OpenDSS validation is limited.”

**Risk.** The archived direct OpenDSS run has 60 trials and a simplified network.

**Mitigation already present.** The run log is archived and checked against CSV output by tests in this branch.

**Next best improvement.** Increase optional OpenDSS trials to at least 500 for the direct check or publish convergence of the p95 THD estimate versus trial count.

**Manuscript guardrail.** Call OpenDSS an independent check of the screening implementation, not full validation of all assumptions.

## Minimum pre-submission checklist

- [ ] Run `pytest -q` on a clean checkout.
- [ ] Run `python scripts/reproduce_all.py` and inspect regenerated figures.
- [ ] Run `python scripts/dynamic_robustness_sweep.py` and confirm the scenario count and rank ordering.
- [ ] Run `python scripts/harmonic_robustness_sweep.py` and confirm the scenario count and rank ordering.
- [ ] If OpenDSSDirect.py is available, run `python scripts/run_true_opendss.py` and compare the p95 order against the archived run log.
- [ ] Regenerate `MANIFEST_SHA256.csv` after final file changes.
- [ ] Deposit a release archive in Zenodo and replace placeholder DOI language.
- [ ] Keep all claims that depend on assumptions tied to the assumption-provenance table.
- [ ] Confirm that no figure is manually edited after code generation.
- [ ] Confirm that all coauthors approve the AI-assisted drafting disclosure.

## Recommended additional experiments before a serious journal submission

1. **Waveform generalization sweep.** Vary communication interval, dip depth, checkpoint cadence, random jitter, and campus phase coherence; report rank-order stability.
2. **Harmonic equalization test.** Hold harmonic spectra fixed across architectures and vary only the number/location of AC-facing converter interfaces, then separately add filtering assumptions.
3. **Direct OpenDSS convergence.** Report p95 THD confidence versus trial count and network-impedance perturbation.
4. **Protection requirements table.** Convert the protection screening into explicit design requirements without claiming that the requirements are already met by commercial equipment.
5. **Cost-neutral counterfactual.** Add a case where local SST plus storage receives a comparable buffer allocation to test whether the DC backbone still has a systems advantage.
6. **Terminology audit.** Replace any accidental “validated,” “proven,” or “compliant” language with “screened,” “bounded,” “reproduced,” or “consistent with.”

## Decision rule for authors

The paper is publication-ready only if the final manuscript can survive the following sentence:

> This is a reproducible architecture-level screening study that identifies when the AC/DC boundary should become a subtransmission planning variable; it does not replace site-specific harmonic, EMT, protection, insulation, or cost studies.

If any abstract, result heading, figure caption, or conclusion promises more than that, revise before submission.
