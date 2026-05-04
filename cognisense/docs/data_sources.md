# CogniSense Data Sources

Every benchmark number in `backend/app/data/research_benchmarks.py` traces back to one of the peer-reviewed or federal sources below. If you cite the project in a report or demo, use these sources directly.

## Age-stratified ADRD prevalence

**Alzheimer's Association. 2024 Alzheimer's Disease Facts and Figures.** *Alzheimer's & Dementia.* 2024;20(5):3708-3821. DOI: 10.1002/alz.13809.

> Among U.S. adults 65+: 5.0% at 65-74, 13.2% at 75-84, 33.4% at 85+. Younger-onset dementia: approximately 110 per 100,000 adults 30-64.

**Rajan KB, Weuve J, Barnes LL, et al.** Population estimate of people with clinical Alzheimer's disease and mild cognitive impairment in the United States (2020-2060). *Alzheimer's & Dementia.* 2021;17(12):1966-1975.

## Race and ethnicity prevalence

**Matthews KA, Xu W, Gaglioti AH, et al.** Racial and ethnic estimates of Alzheimer's disease and related dementias in the United States (2015-2060) in adults aged >=65 years. *Alzheimer's & Dementia.* 2019;15(1):17-24.

> U.S. adults 65+ prevalence by race/ethnicity: Black 13.8%, Hispanic 12.2%, non-Hispanic White 10.3%, AI/AN 9.1%, AAPI 8.4%. Black adults approximately 2x more likely and Hispanic adults approximately 1.5x more likely than White adults to develop AD.

**Mayeda ER, Glymour MM, Quesenberry CP, Whitmer RA.** Inequalities in dementia incidence between six racial and ethnic groups over 14 years. *Alzheimer's & Dementia.* 2016;12(3):216-224.

> Kaiser Permanente Northern California 14-year cohort of 274,283 members. Annual dementia incidence ranged from 15.2 per 1,000 (Asian Americans) to 26.6 per 1,000 (Black adults).

## Subjective cognitive decline

**Taylor CA, Bouldin ED, McGuire LC.** Subjective Cognitive Decline Among Adults Aged >= 45 Years: United States, 2015-2020. *MMWR Morb Mortal Wkly Rep.* 2023;72(10):249-255.

> Age-adjusted SCD prevalence: AI/AN 16.7%, Hispanic 11.4%, Black 10.1%, White 9.3%, AAPI 5.0%. Overall 9.6%.

## Sex and gender

**World Health Organization.** Dementia fact sheet. 2025.

> Women disproportionately affected: higher disability-adjusted life years and mortality. Approximately two-thirds of U.S. Americans 65+ living with Alzheimer's are women (per Alzheimer's Association 2024).

**Brady B, Eramudugolla R, Huque MH, et al.** Sex and gender differences in risk scores for dementia and Alzheimer's disease among cisgender, transgender, and non-binary adults. *Alzheimer's & Dementia.* 2024. DOI: 10.1002/alz.13317.

## Modifiable risk factors (Phase 1 suggestion engine)

**Livingston G, Huntley J, Liu KY, et al.** Dementia prevention, intervention, and care: 2024 report of the Lancet standing Commission. *The Lancet.* 2024;404(10452):572-628. DOI: 10.1016/S0140-6736(24)01296-0.

> Identifies 14 modifiable risk factors accounting for approximately 45% of global dementia cases. Two new factors added in 2024: untreated vision loss and high LDL cholesterol.

## Speech / language biomarkers (Phase 2 model architecture reference)

**Luz S, Haider F, de la Fuente S, et al.** Alzheimer's Dementia Recognition through Spontaneous Speech: The ADReSS Challenge. *Interspeech.* 2020.

**de la Fuente Garcia S, Ritchie CW, Luz S.** Artificial Intelligence, Speech, and Language Processing Approaches to Monitoring Alzheimer's Disease: A Systematic Review. *Journal of Alzheimer's Disease.* 2020;78(4):1547-1574.

## Important caveats

1. **Clinical-symptom based.** The prevalence figures reflect symptom-based diagnoses. Biomarker-confirmed prevalence could be 15-30% lower (Alzheimer's Association 2024).

2. **Under-diagnosis.** Black, Hispanic, AI/AN, and AAPI adults are under-diagnosed in U.S. clinical settings (Lennon et al. 2022; CDC MMWR 2023). Prevalence numbers for those groups likely underestimate true disease burden.

3. **Population vs. individual.** All benchmarks are population-level. A user's score being "better than peer average" does not mean they are healthy; a score "worse than average" does not mean they have dementia. This is why CogniSense centers trajectory analysis against the user's own baseline, not absolute comparison to peers.

4. **APOE and genetics.** The APOE-epsilon-4 allele is a strong predictor in white populations but weaker and inconsistent in Black and Hispanic populations (Crean et al. 2011; Farrer et al. 1997). CogniSense does not collect genetic data.
