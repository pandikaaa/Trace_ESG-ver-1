# Daftar Fitur yang Belum Diimplementasikan

Deliverable #8 brief. Semuanya di luar cakupan MVP atau belum sempat dikerjakan.

## Di luar cakupan MVP (sesuai brief bagian 4)
- Login multi-user, peran (preparer/reviewer), dan jejak persetujuan
- Integrasi ERP dan integrasi otomatis ke sistem pemasok
- Blockchain dan AI generatif
- Kategori Scope 3 selain Kategori 1; Scope 1 dan 2; pilar Social dan Governance

## Belum dikerjakan
- Penyimpanan persisten (SQLite) dan riwayat versi: data hanya hidup selama sesi peramban
- Konversi mata uang asing dan penyesuaian inflasi: spend-based hanya menerima IDR (selain IDR ditolak dengan pesan jelas)
- Faktor emisi resmi: data demo memakai faktor DUMMY. Faktor yang sumbernya dapat ditelusuri harus dipilih dan diverifikasi oleh pengguna/ahli
- Membaca isi dokumen bukti (OCR/ekstraksi): aplikasi hanya mencatat referensi, status, dan hash SHA-256 berkas
- Kuantifikasi ketidakpastian statistik (interval/propagasi): ketidakpastian dinilai kualitatif per metode
- Alokasi, batas organisasi (organizational boundary), dan penilaian materialitas kategori Scope 3 lintas kategori
- Permintaan dokumen otomatis ke pemasok dan pelacakan tindak lanjut
- Ekspor PDF dengan grafik (PDF saat ini berisi tabel dan teks)
- Pengujian performa pada data ribuan baris
- Uji kegunaan dan efisiensi dengan pengguna sungguhan (protokol di `USER_TEST_PROTOCOL.md`)
- Uji tampilan otomatis di peramban (hanya uji asap kode halaman dengan tiruan Streamlit)
