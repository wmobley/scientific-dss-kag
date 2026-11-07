# Crosswalk review sheet

Nothing below is accepted. These are **recommendations from the assistant that built the candidates**, based on the DYNAMO dev catalog's own descriptions (read 2026-11-06) and general domain knowledge. A fixture record counts as aligned to the catalog and to SVO only after a person accepts its entry.

## How to record a decision

```bash
uv run scientific-dss crosswalk-review --domain groundwater-subsidence --list

uv run scientific-dss crosswalk-review --domain groundwater-subsidence \
  --fixture-id urn:example:variable:groundwater-head --status accepted --reviewer "Your Name"
# an entry with several candidates also needs --catalog-id <the candidate's catalog_id>
# --status rejected and --status unreviewed are also available; --date defaults to today (UTC)

DSS_CATALOG_URL=https://mintdevapi.pods.portals.tapis.io/v2.0.0 uv run scientific-dss catalog-verify --domain groundwater-subsidence
```

The command refuses an acceptance without a reviewer or without one of the entry's own candidate IDs. `catalog-verify` then re-checks every ID, label and SVO link against the live catalog. Accepted entries appear under `aligned_after_human_review`.

## groundwater-subsidence (7 entries; the domain used to verify the integration)

| Fixture record | Catalog candidate | SVO link | What the catalog says | Check before accepting | Recommendation |
|---|---|---|---|---|---|
| groundwater head (m) | `groundwater__head` | yes | An SVO-generated description; units not stated in the text | Unit is metres and the vertical datum is the one your model uses | **Accept** |
| land surface subsidence (m) | `land_surface__subsidence` | yes | "Vertical subsidence (downward displacement) of the land surface." | It is a cumulative length, not a rate (the catalog has a separate `land_surface__displacement_rate`); sign convention (downward positive) | **Accept** |
| aquifer hydraulic conductivity (m/d) | `aquifer__hydraulic_conductivity` | yes | "Saturated hydraulic conductivity of the aquifer porous medium." | MODFLOW needs horizontal and vertical values separately; the catalog also has `groundwater__horizontal_hydraulic_conductivity` and `groundwater__vertical_hydraulic_conductivity` | **Accept for the generic concept only**; later split the fixture into horizontal and vertical records before calling it model-ready |
| well pumping volume flow rate (m3/d) | `groundwater_well__pumping_volume_flow_rate` | yes | "Volumetric pumping (withdrawal/injection) rate at a groundwater well." | The catalog covers both directions; MODFLOW treats extraction as negative. State your sign convention | **Accept**, noting the sign convention |
| groundwater drawdown (m) | `groundwater__drawdown` | **no** | "Simulated drawdown relative to initial or reference hydraulic head." | The catalog gives no SVO link for this variable; the record describes simulated output, the fixture is generic; reference head must be stated | **Accept as a catalog link only**; its `svo_uri` stays empty and it must not be reported as SVO-aligned |
| MODFLOW 6 teaching record | `MODFLOW 6` (model) | n/a | "Execution-ready configuration for USGS MODFLOW 6 groundwater simulations in MINT. Uses mf6 as the executable and expects an MF6 simulation with mfsim.nam ..." | It is an execution configuration of the model. Our fixture says "CSUB compaction", and the catalog text does not say whether CSUB is configured | **Accept the identity**; get an expert to confirm CSUB before claiming subsidence capability |
| MODFLOW 2005 teaching record | `MODFLOW 2005` (model) | n/a | "Modflow is a popular open-source groundwater flow model distributed by the U.S. Geological survey" | Our fixture says "SUB compaction"; the catalog text is generic and does not mention SUB | **Accept the identity**; same SUB caveat |

## vector-borne-disease (2 entries; the documented negative case, lower priority)

This domain has no catalog counterparts for habitat, occurrence, SDM models or vector variables (see its `gaps` list), so there is little to align.

| Fixture record | Catalog candidates | Recommendation |
|---|---|---|
| near-surface air temperature (K) | `land_surface_air__temperature` (air above the land surface), `air__temperature` (generic) | **Accept `land_surface_air__temperature`** (the closer scope; pass `--catalog-id`), or leave unreviewed |
| precipitation amount (mm) | `atmosphere_water__time_integral_of_precipitation_leq_volume_flux`, `atmosphere_water__precipitation_leq_volume_flux` | **Reject both for now**: the first is an accumulated depth whose period an expert must fix, the second is a rate. Leaving it unreviewed is also fine |

## What acceptance does and does not mean

Accepting says the catalog record names the same concept as the fixture record. It does not say a model is suitable for a decision, that units and conventions agree in a real run, or that the synthetic fixture values are real. The scope note on `/integrations` already says SVO alignment is unverified until this review is done.
