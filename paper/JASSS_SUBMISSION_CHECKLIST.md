# JASSS Submission Checklist

## 1. Editorial fit

- [x] The paper is framed as a social-simulation and collective-composition study.
- [x] Football is presented as a rule-bounded interdependent task environment, not as the publication field or a betting/prediction application.
- [x] The Synthetic XI is defined as a synthetic collective, not as a team of LLMs or autonomous AI teammates.
- [x] The strongest claim is conditional on the frozen model, data, and assumptions.
- [x] Monte Carlo precision is separated from structural uncertainty.

## 2. Core files completed

- [x] `MANUSCRIPT_JASSS_V1.md`
- [x] `SUPPLEMENT_ODD_OFFICIAL_V1.md`
- [x] `JASSS_SUBMISSION_STRATEGY.md`
- [x] `COVER_LETTER_JASSS.md`
- [x] `JASSS_REFERENCE_AUDIT.md`
- [x] Existing master results report, figures, captions, and provenance matrix

## 3. Double-blind review preparation

JASSS uses double-blind review. The public repository currently contains the owner's identity and therefore should not be linked directly from the anonymized manuscript without an editorial plan.

- [ ] Create a separate anonymous review package containing the exact frozen submission snapshot.
- [ ] Use an anonymous view-only repository link or a supplementary archive whose file metadata do not identify the authors.
- [ ] Remove author names, affiliations, acknowledgments, grant identifiers, personal websites, ORCID, and identifying PDF metadata from the review manuscript.
- [ ] Replace identifying repository language with: “The anonymized model, code, data, and reproduction instructions are provided in the supplementary review repository.”
- [ ] Ensure README files, commit history, environment files, image metadata, and generated manifests in the review package do not expose identity.
- [ ] Retain the public GitHub repository unchanged as the authoritative development history.
- [ ] Tell the editor in the cover letter that an anonymous review snapshot corresponds exactly to a public, hash-verified repository that will be linked after review or acceptance.
- [ ] Do not fabricate anonymity: if the public project is already readily discoverable, disclose this fact confidentially to the editor and follow the editor's preferred procedure.

## 4. Permanent archive

- [ ] Create a final tagged release from the frozen submission commit.
- [ ] Deposit the release in Zenodo or an equivalent preservation repository.
- [ ] Obtain a DOI for the exact version submitted.
- [ ] Include license files for code, data, documentation, and figures.
- [ ] Include `CITATION.cff` with authors, title, version, DOI, repository URL, and release date.
- [ ] Verify that all manifest hashes match the deposited files.
- [ ] Add a minimal reproduction guide with environment, dependency, command, expected output, and approximate computational requirements.
- [ ] Preserve the complete workflow artifacts required to regenerate the compact evidence.

For blind review, the DOI and named archival record may need to be withheld from the anonymized manuscript while remaining available confidentially to the editor.

## 5. Manuscript revision

- [ ] Integrate the priority references listed in `JASSS_REFERENCE_AUDIT.md`.
- [ ] Verify every DOI and bibliographic field through the publisher or Crossref.
- [ ] Check the last three years of JASSS for directly relevant papers and avoid superficial journal-specific citation padding.
- [ ] Add paragraph numbering if required by the current production workflow.
- [ ] Convert Markdown headings, tables, notes, and references to the journal's accepted submission format.
- [ ] Ensure the abstract remains self-contained and does not overclaim external validity.
- [ ] Explain why hypothesis numbering begins at H5.
- [ ] Ensure every number in Results is traceable through `PROVENANCE_MATRIX.md`.
- [ ] Confirm that pooled 60,000-run results are always labeled secondary.
- [ ] Confirm that sensitivity reversals are reported prominently rather than buried in supplementary material.

## 6. Figures and accessibility

- [ ] Export each SVG to the journal's preferred production format at publication quality.
- [ ] Preserve editable vector originals.
- [ ] Use labels, line types, symbols, and direct annotations that remain interpretable without color.
- [ ] Add accessible alt text for each figure.
- [ ] Check font size at final printed dimensions.
- [ ] Ensure uncertainty intervals are visually distinguished from structural ranges.
- [ ] Do not place the confirmatory, replication, pooled, sensitivity, and nested estimates on one scale without labeling their different epistemic roles.

## 7. Methods and ODD quality control

- [x] Main text contains a concise ODD-aligned model overview.
- [x] Supplement contains full ODD structure.
- [ ] Add exact code pointers or line/function references for every ODD submodel.
- [ ] Add a compact data-to-agent mapping diagram or table.
- [ ] Add a verification-and-validation table listing check, purpose, threshold, evidence file, and result.
- [ ] Add computational environment details: Python version, dependency lock, operating system, and hardware class.
- [ ] Run reproduction from a clean environment using only archived materials.
- [ ] Have a second person independently follow the reproduction guide.

## 8. Reporting statements

Prepare final versions of:

- [ ] author contribution statement using CRediT roles;
- [ ] funding statement;
- [ ] conflict-of-interest statement;
- [ ] ethics statement;
- [ ] data availability statement;
- [ ] code availability statement;
- [ ] preregistration statement;
- [ ] AI/computational-assistance statement aligned with the journal's current policy;
- [ ] acknowledgment section for the non-anonymized version.

## 9. Separate title page

- [ ] Manuscript title
- [ ] Full author names
- [ ] Institutional affiliations
- [ ] Corresponding-author email
- [ ] ORCID identifiers
- [ ] Running title
- [ ] Word count
- [ ] Number of figures, tables, and supplementary files
- [ ] Author contributions
- [ ] Funding and conflicts

## 10. Final scientific audit

- [ ] Confirm the official source revision remains `06c750cfef3246d3c6112f6bd86d25a83287308f`.
- [ ] Confirm the confirmatory evidence revision remains `0461ed7b5cf796cd4ab484eeca4ceb5a8075e41b`.
- [ ] Confirm the replication evidence revision remains `7c55141d9a597deaf25058a2eec28f1d945af093`.
- [ ] Confirm no scientific source, parameter, roster, seed, or result has changed during editorial work.
- [ ] Recalculate all displayed percentages from frozen machine-readable files.
- [ ] Compare manuscript tables and figure labels against source JSON/CSV files.
- [ ] Confirm post-result tuning remains recorded as false.
- [ ] Confirm the confirmatory run remains primary and the 50,000-run result remains an independent precision replication.

## 11. Submission decision rule

Submit to JASSS when:

1. the manuscript and ODD have passed an independent reproduction review;
2. the anonymous review package is identity-scrubbed and hash-equivalent to the frozen release;
3. the literature and DOI audit is complete;
4. the archive strategy has been communicated accurately to the editor;
5. every substantive claim is linked to frozen evidence;
6. no unresolved language implies physical-world prediction or “AI versus humans.”
