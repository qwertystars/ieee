# Model Data Licensing — Calibration Datasets

Public real flood/damage datasets sourced for conformal calibration of the
platform's ML models. Each dataset is documented with its source URL, license,
acquisition method, and which model it calibrates.

## Dataset Summary

| Dataset | License | Acquisition | Calibrates | Status |
|---|---|---|---|---|
| Sen1Floods11 | CC BY 4.0 | Direct download (GCS HTTPS) | sar-flood-mapping | Downloaded |
| xBD | Non-commercial research | Registration required (xView2) | building-damage | Gated |
| UNOSAT Flood Products | Per-product | Registration required | sar-flood-mapping (supplementary) | Gated |
| Copernicus EMS | Per-product | Registration required | building-damage (supplementary) | Gated |
| incident-nlp | N/A | No public dataset identified | incident-nlp | No data |

---

## Sen1Floods11

- **Name:** Sen1Floods11: A Georeferenced Dataset to Train and Test Deep Learning
  Flood Algorithms for Sentinel-1
- **Source URL:** https://github.com/cloudtostreet/Sen1Floods11
- **Data URL:** `gs://sen1floods11/` (Google Cloud Storage, public)
- **HTTPS access:** `https://storage.googleapis.com/sen1floods11/`
- **License:** CC BY 4.0 (Creative Commons Attribution 4.0 International)
- **Citation:** Bonafilia, D., Tellman, B., Anderson, T., Issenberg, E. 2020.
  "Sen1Floods11: a georeferenced dataset to train and test deep learning flood
  algorithms for Sentinel-1." The IEEE/CVF Conference on Computer Vision and
  Pattern Recognition (CVPR) Workshops, 2020, pp. 210-211.
- **Acquisition method:** Direct download via HTTPS from the public GCS bucket.
  No registration or authentication required. The dataset contains 446
  hand-labeled chips (512x512 GeoTIFFs) across 11 flood events (Bolivia, Ghana,
  India, Mekong, Nigeria, Pakistan, Paraguay, Somalia, Spain, Sri-Lanka, USA).
  Each chip has paired Sentinel-1 SAR imagery (VV/VH bands, float32) and a
  hand-labeled binary flood mask (-1=NoData, 0=NotWater, 1=Water, int16).
- **Calibrates:** `sar-flood-mapping` model. Features extracted per chip:
  mean VV backscatter, mean VH backscatter, VV-VH difference, std VV, std VH.
  Target: water fraction (fraction of valid pixels labeled as flood).
- **Downloaded:** Subset of 60 chips (balanced across events) stored under
  `backend/data/calibration/sen1floods11/`. Manifest with SHA256 checksums at
  `backend/data/calibration/manifest.json`. Not committed to git (gitignored).
- **License compliance:** CC BY 4.0 permits commercial use, modification, and
  redistribution with attribution. The citation above is included in this
  document and in the download script header.

## xBD

- **Name:** xBD: A Dataset for Assessing Building Damage from Satellite Imagery
- **Source URL:** https://xview2.org/dataset
- **License:** Non-commercial research license (xView2 license agreement)
- **Acquisition method:** Registration required at https://xview2.org/dataset.
  Users must create an account and agree to the xView2 license terms before
  downloading. The dataset contains pre/post satellite imagery with building
  damage labels from 19 disaster events (~850,000 building polygons).
- **Calibrates:** `building-damage` model. Would provide paired pre/post
  imagery with damage classification labels (no-damage, minor, major,
  destroyed) for conformal calibration of damage assessment predictions.
- **Status:** Registration-gated. Not downloaded. The download script documents
  the registration gate and skips this dataset automatically.
- **License compliance:** Non-commercial research license restricts use to
  academic and research purposes. Commercial deployment requires separate
  licensing from the xView2 program.

## UNOSAT Flood Products

- **Name:** UNOSAT Rapid Mapping Service — Flood Products
- **Source URL:** https://unosat.org/products
- **License:** Per-product (varies by product)
- **Acquisition method:** Registration and request required. UNOSAT products
  are distributed through the UNOSAT website and require an account. Some
  products are publicly accessible; others require formal request.
- **Calibrates:** `sar-flood-mapping` model (supplementary). UNOSAT flood
  extent products provide vector-based flood delineation maps derived from
  satellite imagery, which could supplement Sen1Floods11 for regional
  calibration.
- **Status:** Registration-gated. Not downloaded. Documented as a supplementary
  source for future calibration expansion.

## Copernicus EMS

- **Name:** Copernicus Emergency Management Service — Rapid Mapping
- **Source URL:** https://emergency.copernicus.eu
- **License:** Per-product (Copernicus EMS terms and conditions)
- **Acquisition method:** Registration and request required. Copernicus EMS
  products are accessible through the EMS portal. Some products are freely
  downloadable; others require formal request through the EMS activation
  pages.
- **Calibrates:** `building-damage` model (supplementary). Copernicus EMS
  grading products provide damage assessment maps derived from satellite
  imagery, which could supplement xBD for regional calibration.
- **Status:** Registration-gated. Not downloaded. Documented as a supplementary
  source for future calibration expansion.

## incident-nlp

- **Name:** No public dataset identified for NLP calibration
- **Source URL:** N/A
- **License:** N/A
- **Acquisition method:** No public dataset of incident reports with
  ground-truth classifications was identified for calibrating the incident-nlp
  model. The incident-nlp model parses free-text incident reports into
  structured fields (disaster type, severity, location). Calibrating its
  prediction confidence would require a labeled corpus of incident reports
  with verified structured outputs, which is not publicly available.
- **Calibrates:** `incident-nlp` model (no calibration data available)
- **Status:** No data. The calibration feature for incident-nlp is marked
  `degraded` — conformal intervals are not available for NLP predictions
  until a suitable labeled corpus is acquired or created.

---

## Attribution

Sen1Floods11 data is used under the CC BY 4.0 license. The required attribution
is provided in this document and in the header of `scripts/download_calibration_datasets.py`.

xBD, UNOSAT, and Copernicus EMS data is NOT included in this repository. The
above documentation is for reference only. If you obtain access to these
datasets through their respective registration processes, ensure you comply
with their license terms before use.
