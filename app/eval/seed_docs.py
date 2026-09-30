"""Generate a synthetic, PII-free chat-style corpus: PDFs (text layer) + receipt photos (OCR path).

All names/numbers are fictional; phone/account numbers are masked by design.
Writes data/<tenant>/docs/*.pdf, data/<tenant>/receipts/*.png and data/<tenant>/manifest.json
(created_at + channel metadata the real platform would get from the message event).
"""
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent / "data"
# dates are relative to seeding time so "kemarin"/"minggu lalu" work in a live demo; eval pins QUERY_NOW to this
# anchored at 12:00 WIB today; ts() subtracts 0-8 h, so an item stays inside its WIB calendar day
NOW = datetime.now(timezone(timedelta(hours=7))).replace(hour=12, minute=0, second=0, microsecond=0)
random.seed(7)

DOCS = {
    "tenant_demo": {
        "INV-2026-0912_refund_sepatu.pdf": ("whatsapp", 3, [
            "INVOICE PENGEMBALIAN DANA (REFUND) No. INV-2026-0912",
            "Toko Lari Cepat - Pelanggan: Budi S. (nomor disamarkan)",
            "Produk: Sepatu lari RunMax 2 warna merah ukuran 42",
            "Alasan: ukuran tidak sesuai, barang dikembalikan dalam kondisi baru",
            "Jumlah refund: Rp 899.000 ditransfer ke rekening pelanggan dalam 3 hari kerja",
        ]),
        "Kebijakan_Pengembalian_Barang.pdf": ("crm", 40, [
            "KEBIJAKAN PENGEMBALIAN BARANG DAN RETUR",
            "Pelanggan dapat mengajukan retur maksimal 7 hari setelah barang diterima.",
            "Barang harus dalam kondisi baru, lengkap dengan label dan kemasan asli.",
            "Produk promo, pakaian dalam, dan kosmetik yang sudah dibuka tidak dapat diretur.",
            "Ongkos kirim retur ditanggung toko apabila barang cacat atau salah kirim.",
        ]),
        "SOP_Eskalasi_Komplain.pdf": ("crm", 55, [
            "SOP ESKALASI KOMPLAIN PELANGGAN",
            "Level 1: agen menjawab dalam 5 menit dan mencatat tiket di CRM.",
            "Level 2: jika belum selesai dalam 24 jam, eskalasi ke supervisor.",
            "Level 3: komplain berulang atau ancaman viral di media sosial diteruskan ke manajer.",
            "Semua eskalasi wajib diberi tag 'komplain' dan prioritas tinggi.",
        ]),
        "Katalog_Skincare_Glowin.pdf": ("instagram", 20, [
            "KATALOG PRODUK SKINCARE GLOWIN 2026",
            "Serum vitamin C 20ml - Rp 129.000 - mencerahkan kulit kusam",
            "Sunscreen SPF 50 PA++++ 50ml - Rp 99.000 - ringan dan tidak lengket",
            "Moisturizer gel untuk kulit berminyak dan berjerawat - Rp 89.000",
            "Paket bundling hemat: serum + sunscreen diskon 15 persen",
        ]),
        "Label_Pengiriman_Kurir.pdf": ("whatsapp", 1, [
            "LABEL PENGIRIMAN - RESI JX-7781-2290",
            "Pengirim: Gudang Cikarang. Penerima: Sari W., Bandung (alamat disamarkan)",
            "Isi paket: blender dapur 2 liter, berat 3 kg, asuransi pengiriman aktif",
            "Layanan: reguler 2-3 hari. Mohon tangani dengan hati-hati, barang pecah belah",
        ]),
        "Kontrak_Langganan_WhatsApp_API.pdf": ("crm", 70, [
            "PERJANJIAN BERLANGGANAN LAYANAN WHATSAPP BUSINESS API",
            "Paket: Enterprise 20 agen, masa kontrak 12 bulan, perpanjangan otomatis",
            "Biaya percakapan dibebankan per sesi sesuai tarif Meta yang berlaku",
            "SLA ketersediaan platform 99,5 persen per bulan dengan kompensasi kredit",
            "Pemutusan kontrak wajib diberitahukan 30 hari sebelumnya secara tertulis",
        ]),
        "Laporan_SLA_Agen_Agustus.pdf": ("crm", 29, [
            "LAPORAN SLA DAN PERFORMA AGEN - AGUSTUS 2026",
            "Rata-rata waktu respon pertama: 2 menit 40 detik",
            "Rata-rata waktu penyelesaian: 3 jam 15 menit, 92 persen tiket memenuhi SLA",
            "Agen terbaik bulan ini: tim divisi Retail, CSAT 4,8 dari 5",
            "Kanal dengan volume tertinggi: WhatsApp 71 persen, Instagram 18 persen",
        ]),
        "Penawaran_Harga_Laptop_Kantor.pdf": ("email", 12, [
            "SURAT PENAWARAN HARGA (QUOTATION) Q-2026-118",
            "Pengadaan 25 unit laptop kantor prosesor 8 core, RAM 16GB, SSD 512GB",
            "Harga satuan Rp 11.500.000, total Rp 287.500.000 belum termasuk PPN",
            "Garansi resmi 3 tahun, pengiriman 14 hari kerja setelah PO",
        ]),
        "Panduan_Reset_Password.pdf": ("crm", 90, [
            "PANDUAN RESET PASSWORD AKUN PELANGGAN",
            "Buka halaman login lalu klik 'Lupa password'.",
            "Masukkan email terdaftar, tautan reset berlaku selama 30 menit.",
            "Jika tautan tidak diterima, periksa folder spam atau hubungi agen.",
            "Agen dilarang meminta kode OTP atau password pelanggan.",
        ]),
        "Script_Broadcast_Promo_1212.pdf": ("whatsapp", 8, [
            "SCRIPT BROADCAST WHATSAPP PROMO HARBOLNAS 12.12",
            "Halo Kak! Diskon hingga 70 persen + gratis ongkir khusus tanggal 12 Desember.",
            "Gunakan kode voucher HEMAT1212 untuk potongan tambahan Rp 50.000.",
            "Balas STOP untuk berhenti menerima pesan promo.",
        ]),
        "Invoice_Catering_Kantor.pdf": ("email", 15, [
            "INVOICE CATERING - DAPUR BUNDA",
            "Pesanan makan siang kantor 120 porsi nasi kotak ayam bakar",
            "Tambahan 120 gelas es teh manis dan buah potong",
            "Total tagihan Rp 5.400.000, jatuh tempo 14 hari",
        ]),
        "Kartu_Garansi_Kulkas.pdf": ("whatsapp", 33, [
            "KARTU GARANSI RESMI LEMARI ES 2 PINTU",
            "Garansi kompresor 10 tahun, garansi sparepart 1 tahun",
            "Klaim garansi dengan menunjukkan kartu ini dan nota pembelian",
            "Kerusakan akibat banjir, petir, atau pemakaian tidak wajar tidak ditanggung",
        ]),
        "Jadwal_Pengiriman_Ulang.pdf": ("whatsapp", 2, [
            "PEMBERITAHUAN PENGIRIMAN ULANG",
            "Paket gagal dikirim karena penerima tidak di tempat.",
            "Pengiriman ulang dijadwalkan besok antara jam 09.00 - 15.00.",
            "Jika gagal lagi, paket akan dikembalikan ke gudang pengirim.",
        ]),
        "FAQ_Pembayaran_Virtual_Account.pdf": ("crm", 60, [
            "FAQ PEMBAYARAN VIRTUAL ACCOUNT",
            "Nomor virtual account berlaku 24 jam sejak pesanan dibuat.",
            "Pembayaran dikonfirmasi otomatis dalam 5-10 menit.",
            "Jika saldo terpotong tetapi status belum lunas, kirim bukti transfer ke agen.",
        ]),
        "Notulen_Onboarding_Klien.pdf": ("email", 5, [
            "NOTULEN RAPAT ONBOARDING KLIEN BARU",
            "Agenda: integrasi chatbot, pembuatan template WhatsApp, pelatihan agen",
            "Keputusan: go-live chatbot tanggal 15 Oktober, pelatihan 2 sesi",
            "Tindak lanjut: tim teknis menyiapkan webhook dan akun sandbox",
        ]),
        "Bali_Offsite_Itinerary.pdf": ("email", 25, [
            "TEAM OFFSITE ITINERARY - BALI",
            "Day 1: arrival at Ngurah Rai airport, check-in at beach resort in Nusa Dua",
            "Day 2: team building activities, sunset dinner at Jimbaran",
            "Day 3: temple visit in Uluwatu and flight back to Jakarta",
        ]),
        "Privacy_Notice_Data_Processing.pdf": ("crm", 100, [
            "PRIVACY NOTICE - PERSONAL DATA PROCESSING",
            "We process customer personal data to provide omnichannel support services.",
            "Data subjects may request access, correction, or deletion of their data.",
            "Data is stored in Indonesia and retained according to our retention policy.",
        ]),
        "Damaged_Package_Claim_Form.pdf": ("email", 4, [
            "DAMAGED PACKAGE CLAIM FORM",
            "The parcel arrived with a crushed box and a broken glass vase inside.",
            "Customer attached unboxing video and photos as evidence.",
            "Requested resolution: replacement item shipped with extra bubble wrap.",
        ]),
        "Tagihan_Listrik_Kantor.pdf": ("email", 18, [
            "TAGIHAN LISTRIK KANTOR - SEPTEMBER 2026",
            "Pemakaian 4.820 kWh, daya terpasang 33.000 VA",
            "Total tagihan Rp 7.230.000, bayar sebelum tanggal 20",
        ]),
        "Menu_Kafe_Senja.pdf": ("instagram", 45, [
            "MENU KAFE SENJA",
            "Kopi susu gula aren Rp 22.000, americano Rp 20.000, matcha latte Rp 28.000",
            "Roti bakar cokelat keju Rp 25.000, pisang goreng madu Rp 18.000",
            "Buka setiap hari jam 08.00 - 22.00, wifi gratis",
        ]),
    },
    "tenant_other": {
        "Refund_Invoice_Other_Company.pdf": ("whatsapp", 3, [
            "INVOICE REFUND - PT LAIN SEJAHTERA",
            "Refund sepatu lari warna merah, dana dikembalikan ke pelanggan",
        ]),
        "Kebijakan_Retur_Other.pdf": ("crm", 10, [
            "KEBIJAKAN RETUR BARANG PT LAIN SEJAHTERA",
            "Retur diterima maksimal 14 hari setelah barang diterima",
        ]),
    },
}

RECEIPTS = {
    "struk_minimarket.png": ("whatsapp", 6, ["MINIMARKET SERBA ADA", "Susu UHT 1L       18.500", "Roti tawar        15.000",
                                             "Telur 1kg         29.000", "TOTAL             62.500", "TUNAI             70.000"]),
    "struk_bensin.png": ("whatsapp", 9, ["SPBU 34-17102", "PERTAMAX", "Liter      20.00", "Harga/L   13.900",
                                         "Total   Rp 278.000", "Terima kasih"]),
    "bukti_transfer_bank.png": ("whatsapp", 1, ["BUKTI TRANSFER BERHASIL", "Tujuan: TOKO LARI CEPAT", "Rek: ****-****-1234",
                                                "Nominal: Rp 899.000", "Berita: pembayaran sepatu"]),
    "nota_bengkel_motor.png": ("whatsapp", 14, ["BENGKEL MOTOR JAYA", "Ganti oli mesin    55.000", "Kampas rem depan   45.000",
                                                "Servis CVT         60.000", "TOTAL             160.000"]),
    "struk_kopi.png": ("instagram", 11, ["KOPI SENJA", "Es kopi susu x2    44.000", "Croissant x1       27.000", "TOTAL              71.000"]),
    "tiket_parkir_mall.png": ("whatsapp", 20, ["TIKET PARKIR", "MALL GRAND CITY", "Masuk 10:12", "Keluar 13:40", "Mobil  Rp 15.000"]),
    "struk_apotek.png": ("whatsapp", 7, ["APOTEK SEHAT", "Paracetamol 500mg  12.000", "Obat batuk sirup    28.000",
                                         "Vitamin C          35.000", "TOTAL              75.000"]),
    "resi_ojek_online.png": ("whatsapp", 0, ["PERJALANAN SELESAI", "Dari: Stasiun Sudirman", "Ke: Kantor Kuningan",
                                             "Jarak 6.2 km", "Tarif Rp 24.000"]),
}


def ts(days_ago):
    return (NOW - timedelta(days=days_ago, hours=random.randint(0, 8))).isoformat()


def write_pdf(path, lines):
    c = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, lines[0])
    c.setFont("Helvetica", 11)
    for line in lines[1:]:
        y -= 26
        c.drawString(50, y, line)
    c.save()


def write_receipt(path, lines):
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 26)
    except OSError:
        font = ImageFont.load_default()
    img = Image.new("RGB", (620, 90 + 48 * len(lines)), (250, 248, 240))
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((40, 40 + 48 * i), line, fill=(20, 20, 20), font=font)
    img.rotate(random.uniform(-2, 2), expand=True, fillcolor=(200, 200, 200)).save(path)


def main():
    for tenant, docs in DOCS.items():
        manifest = {}
        ddir = ROOT / tenant / "docs"
        ddir.mkdir(parents=True, exist_ok=True)
        for name, (channel, days, lines) in docs.items():
            write_pdf(ddir / name, lines)
            manifest[f"docs/{name}"] = {"channel": channel, "created_at": ts(days)}
        if tenant == "tenant_demo":
            rdir = ROOT / tenant / "receipts"
            rdir.mkdir(parents=True, exist_ok=True)
            for name, (channel, days, lines) in RECEIPTS.items():
                write_receipt(rdir / name, lines)
                manifest[f"receipts/{name}"] = {"channel": channel, "created_at": ts(days)}
            pdir = ROOT / tenant / "photos"
            for p in sorted(pdir.glob("*.jpg")) if pdir.exists() else []:
                manifest[f"photos/{p.name}"] = {"channel": random.choice(["whatsapp", "instagram"]),
                                                "created_at": ts(random.randint(0, 80))}
        (ROOT / tenant / "manifest.json").write_text(json.dumps(manifest, indent=1))
        print(tenant, len(manifest), "files")
    (ROOT / "seeded_at.txt").write_text(NOW.isoformat())


if __name__ == "__main__":
    main()
