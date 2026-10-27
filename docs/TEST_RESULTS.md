# Hasil Pengujian TRACE ESG

Dijalankan: 2026-10-27 10:00 · Python 3.13.17 · pandas 3.0.5

Perintah: `python scripts/run_evaluation.py` (atau `python -m unittest discover -s tests`).

## 1. Ringkasan tes otomatis

- Total tes: **72** · gagal: **0** · error: **0** · status: **LULUS** (3.7 dtk)
- Cakupan: perhitungan, validasi, mesin risiko, laporan/ekspor, metrik brief, dan uji asap seluruh halaman UI (memakai tiruan Streamlit, lihat keterbatasan).

### Matriks kasus uji yang diminta brief

| Kasus uji | Tes yang mencakup |
|---|---|
| Data valid | `test_valid_data_has_no_issues`, `test_valid_physical_row`, `test_brief_example_500kg_x_2` |
| Kolom/nilai kosong | `test_blank_required_field`, `test_missing_required_column`, `test_missing_or_invalid_inputs_rejected` |
| Transaksi duplikat | `test_exact_duplicate_id_same_content`, `test_same_content_different_id`, `test_duplicate_excluded_by_default_and_togglable` |
| Satuan tidak cocok | `test_unit_mismatch_rejected_no_number`, `test_incompatible_units_raise`, `test_physical_data_never_multiplied_by_spend_factor` |
| Faktor emisi hilang / tanpa sumber | `test_missing_factor_category`, `test_factor_without_source_flagged` |
| Bukti tidak tersedia | `test_evidence_never_verified`, `test_provided_without_reference_is_not_recorded`, `test_attached_document_is_still_unverified` |
| Metode estimasi | `test_spend_based_row`, `test_each_required_finding_type_is_produced` |
| Determinisme & reproduksi | `test_deterministic`, `test_decimal_exactness`, `test_result_stores_reproducibility_fields`, `test_report_is_deterministic` |
| Tidak ada klaim 'terverifikasi' | `test_no_verified_claims`, `test_disclaimer_present_top_and_bottom` |

## 2. Metrik keberhasilan internal (brief bagian 11)

Target adalah sasaran awal internal, bukan standar industri. Pengukuran dilakukan pada dataset sintetis (`data/sample_transactions.csv`, 100 baris, 20 pemasok) dengan faktor emisi DUMMY.

| Metrik | Target | Hasil terukur | Status |
|---|---|---|---|
| Akurasi kalkulasi vs hitung manual independen | 100% | 95 dari 95 baris cocok (100%); baris yang seharusnya ditolak juga ditolak | Tercapai |
| Deteksi anomali tertanam | >= 90% | 86 dari 86 (100.0%) | Tercapai |
| Keterlacakan: rantai input-faktor-metode lengkap | >= 95% | 83 dari 83 transaksi terhitung (100%) | Tercapai |
| Efisiensi dibanding proses manual | lebih rendah dari manual | **Belum diukur** (perlu uji waktu dengan pengguna) | Belum |
| Kegunaan: keberhasilan tugas inti | >= 80% | **Belum diukur** (perlu uji pengguna; lihat `docs/USER_TEST_PROTOCOL.md`) | Belum |

Rincian deteksi anomali per jenis:

| Jenis anomali | Terdeteksi | Total |
|---|---|---|
| duplicate_transaction | 7 | 7 |
| estimation_method_used | 38 | 38 |
| evidence_missing | 17 | 17 |
| inconsistent_reporting_period | 3 | 3 |
| invalid_value | 2 | 2 |
| missing_factor_or_source | 8 | 8 |
| missing_required_field | 4 | 4 |
| unit_mismatch | 7 | 7 |

## 3. Hasil analisis dataset demo

- Total estimasi emisi (belum diverifikasi): **1,129.61 t CO2e** (faktor DUMMY).
- Baris: 100 · dihitung: 83 · ditolak: 12 · duplikat dikecualikan: 5.
- Temuan: 101 (prioritas Tinggi 14 / Sedang 39 / Rutin 48).

## 4. Keterbatasan pengujian (jujur)

- **Anomali ditanam oleh tim sendiri**, jadi angka deteksi 100% bersifat optimistis. Angka ini membuktikan tidak ada regresi dan aturan bekerja pada pola yang diketahui, bukan performa pada data nyata yang berantakan.
- **Akurasi kalkulasi** diuji terhadap implementasi 'hitung manual' independen (tanpa pandas/Decimal) dan contoh deterministik; ini menguji kebenaran aritmetika dan aturan satuan, bukan kebenaran faktor emisi (faktor demo adalah DUMMY).
- **Uji UI** memakai tiruan modul Streamlit: memastikan semua jalur kode halaman berjalan tanpa exception. Uji ini TIDAK menilai tampilan visual, kompatibilitas versi Streamlit, maupun interaksi di peramban. Lakukan uji manual dengan `streamlit run app.py` dan, bila memungkinkan, `streamlit.testing.v1.AppTest`.
- **Efisiensi dan kegunaan** memerlukan partisipan manusia dan belum diukur; jangan dilaporkan sebagai hasil sebelum diuji.
- Dataset hanya 100 baris; performa dan perilaku pada data ribuan baris belum diuji.

## 5. Log eksekusi tes

```
test_all_pages_with_demo_data (test_app_smoke.TestAppSmoke.test_all_pages_with_demo_data) ... ok
test_all_pages_without_data (test_app_smoke.TestAppSmoke.test_all_pages_without_data) ... ok
test_broken_csv_shows_actionable_error_not_crash (test_app_smoke.TestAppSmoke.test_broken_csv_shows_actionable_error_not_crash) ... ok
test_csv_upload_flow (test_app_smoke.TestAppSmoke.test_csv_upload_flow) ... ok
test_empty_file_does_not_crash (test_app_smoke.TestAppSmoke.test_empty_file_does_not_crash) ... ok
test_evidence_upload_marks_unverified_not_verified (test_app_smoke.TestAppSmoke.test_evidence_upload_marks_unverified_not_verified) ... ok
test_reset_button (test_app_smoke.TestAppSmoke.test_reset_button) ... ok
test_whatif_calculator_and_manual_form (test_app_smoke.TestAppSmoke.test_whatif_calculator_and_manual_form) ... ok
test_deterministic (test_calculator.TestCalculateRows.test_deterministic) ... ok
test_duplicate_excluded_by_default_and_togglable (test_calculator.TestCalculateRows.test_duplicate_excluded_by_default_and_togglable) ... ok
test_factor_without_source_flagged (test_calculator.TestCalculateRows.test_factor_without_source_flagged) ... ok
test_missing_factor_category (test_calculator.TestCalculateRows.test_missing_factor_category) ... ok
test_missing_or_invalid_inputs_rejected (test_calculator.TestCalculateRows.test_missing_or_invalid_inputs_rejected) ... ok
test_non_idr_spend_rejected_without_fx (test_calculator.TestCalculateRows.test_non_idr_spend_rejected_without_fx) ... ok
test_old_factor_flagged (test_calculator.TestCalculateRows.test_old_factor_flagged) ... ok
test_physical_data_never_multiplied_by_spend_factor (test_calculator.TestCalculateRows.test_physical_data_never_multiplied_by_spend_factor) ... ok
test_primary_supplier_factor_without_evidence_has_no_source (test_calculator.TestCalculateRows.test_primary_supplier_factor_without_evidence_has_no_source) ... ok
test_primary_with_supplier_factor (test_calculator.TestCalculateRows.test_primary_with_supplier_factor) ... ok
test_primary_without_supplier_factor_falls_back_and_flags (test_calculator.TestCalculateRows.test_primary_without_supplier_factor_falls_back_and_flags) ... ok
test_result_stores_reproducibility_fields (test_calculator.TestCalculateRows.test_result_stores_reproducibility_fields) ... ok
test_spend_based_row (test_calculator.TestCalculateRows.test_spend_based_row) ... ok
test_unit_conversion_documented (test_calculator.TestCalculateRows.test_unit_conversion_documented) ... ok
test_unit_mismatch_rejected_no_number (test_calculator.TestCalculateRows.test_unit_mismatch_rejected_no_number) ... ok
test_valid_physical_row (test_calculator.TestCalculateRows.test_valid_physical_row) ... ok
test_brief_example_500kg_x_2 (test_calculator.TestComputeEmission.test_brief_example_500kg_x_2) ... ok
test_decimal_exactness (test_calculator.TestComputeEmission.test_decimal_exactness) ... ok
test_incompatible_units_raise (test_calculator.TestComputeEmission.test_incompatible_units_raise) ... ok
test_m3_to_litre (test_calculator.TestComputeEmission.test_m3_to_litre) ... ok
test_split_factor_unit (test_calculator.TestComputeEmission.test_split_factor_unit) ... ok
test_ton_to_kg (test_calculator.TestComputeEmission.test_ton_to_kg) ... ok
test_bad_library_schema (test_calculator.TestFactorLibrary.test_bad_library_schema) ... ok
test_bad_value_reported (test_calculator.TestFactorLibrary.test_bad_value_reported) ... ok
test_demo_library_valid_and_labelled_dummy (test_calculator.TestFactorLibrary.test_demo_library_valid_and_labelled_dummy) ... ok
test_anomaly_detection_rate_at_least_90pct (test_metrics.TestMetrics.test_anomaly_detection_rate_at_least_90pct) ... ok
test_calculation_accuracy_matches_manual_100pct (test_metrics.TestMetrics.test_calculation_accuracy_matches_manual_100pct) ... ok
test_every_anomaly_type_has_full_recall (test_metrics.TestMetrics.test_every_anomaly_type_has_full_recall) ... ok
test_sample_data_contains_all_required_variations (test_metrics.TestMetrics.test_sample_data_contains_all_required_variations) ... ok
test_total_equals_sum_of_rows (test_metrics.TestMetrics.test_total_equals_sum_of_rows) ... ok
test_traceability_chain_at_least_95pct (test_metrics.TestMetrics.test_traceability_chain_at_least_95pct) ... ok
test_csv_exports (test_reporting.TestReporting.test_csv_exports) ... ok
test_disclaimer_present_top_and_bottom (test_reporting.TestReporting.test_disclaimer_present_top_and_bottom) ... ok
test_no_verified_claims (test_reporting.TestReporting.test_no_verified_claims) ... ok
test_pdf_valid (test_reporting.TestReporting.test_pdf_valid) ... ok
test_readiness_indicators_not_a_score (test_reporting.TestReporting.test_readiness_indicators_not_a_score) ... ok
test_report_is_deterministic (test_reporting.TestReporting.test_report_is_deterministic) ... ok
test_required_sections (test_reporting.TestReporting.test_required_sections) ... ok
test_clean_row_only_has_no_findings_other_than_none (test_risk_engine.TestFindings.test_clean_row_only_has_no_findings_other_than_none) ... ok
test_each_required_finding_type_is_produced (test_risk_engine.TestFindings.test_each_required_finding_type_is_produced) ... ok
test_every_finding_has_severity_reason_transaction_recommendation (test_risk_engine.TestFindings.test_every_finding_has_severity_reason_transaction_recommendation) ... ok
test_priority_reason_explains_materiality_and_weakness (test_risk_engine.TestFindings.test_priority_reason_explains_materiality_and_weakness) ... ok
test_attached_document_is_still_unverified (test_risk_engine.TestNoAssuranceClaims.test_attached_document_is_still_unverified) ... ok
test_evidence_never_verified (test_risk_engine.TestNoAssuranceClaims.test_evidence_never_verified) ... ok
test_provided_without_reference_is_not_recorded (test_risk_engine.TestNoAssuranceClaims.test_provided_without_reference_is_not_recorded) ... ok
test_quality_has_dimensions_and_no_composite_score (test_risk_engine.TestNoAssuranceClaims.test_quality_has_dimensions_and_no_composite_score) ... ok
test_successful_calculation_does_not_imply_good_traceability (test_risk_engine.TestNoAssuranceClaims.test_successful_calculation_does_not_imply_good_traceability) ... ok
test_invalid_thresholds_rejected (test_risk_engine.TestPriorityRules.test_invalid_thresholds_rejected) ... ok
test_large_emission_weak_evidence_is_high_priority (test_risk_engine.TestPriorityRules.test_large_emission_weak_evidence_is_high_priority) ... ok
test_low_emission_minor_gap_is_routine (test_risk_engine.TestPriorityRules.test_low_emission_minor_gap_is_routine) ... ok
test_matrix (test_risk_engine.TestPriorityRules.test_matrix) ... ok
test_thresholds_are_configurable (test_risk_engine.TestPriorityRules.test_thresholds_are_configurable) ... ok
test_blank_required_field (test_validation.TestValidation.test_blank_required_field) ... ok
test_exact_duplicate_id_same_content (test_validation.TestValidation.test_exact_duplicate_id_same_content) ... ok
test_invalid_types (test_validation.TestValidation.test_invalid_types) ... ok
test_missing_required_column (test_validation.TestValidation.test_missing_required_column) ... ok
test_period_inconsistency (test_validation.TestValidation.test_period_inconsistency) ... ok
test_same_content_different_id (test_validation.TestValidation.test_same_content_different_id) ... ok
test_same_id_different_content_not_excluded (test_validation.TestValidation.test_same_id_different_content_not_excluded) ... ok
test_sample_dataset_shape (test_validation.TestValidation.test_sample_dataset_shape) ... ok
test_semicolon_csv_and_header_normalisation (test_validation.TestValidation.test_semicolon_csv_and_header_normalisation) ... ok
test_unit_table (test_validation.TestValidation.test_unit_table) ... ok
test_unknown_unit_is_warning (test_validation.TestValidation.test_unknown_unit_is_warning) ... ok
test_valid_data_has_no_issues (test_validation.TestValidation.test_valid_data_has_no_issues) ... ok

----------------------------------------------------------------------
Ran 72 tests in 3.748s

OK
```
