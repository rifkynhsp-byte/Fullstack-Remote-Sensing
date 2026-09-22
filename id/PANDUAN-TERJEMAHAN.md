# Panduan Penerjemahan dan Istilah

Dokumen kerja untuk edisi Bahasa Indonesia. Tujuannya satu: agar edisi Indonesia terbaca seperti ditulis orang Indonesia yang memang bekerja di bidang ini, bukan seperti hasil terjemahan mesin dari naskah Inggris.

## Prinsip utama

**Terjemahkan gagasannya, bukan kalimatnya.** Kalau kalimat Inggrisnya panjang dan bercabang, kalimat Indonesianya boleh dipecah. Kalau ada idiom Inggris yang tidak punya padanan, ganti dengan cara orang Indonesia menyampaikan maksud yang sama. Yang harus sama adalah isinya, termasuk semua angka, nama dataset, dan peringatan teknis.

**Panjangnya setara, bukan diringkas.** Edisi Indonesia bukan ringkasan edisi Inggris. Kalau satu bab Inggris punya lima peringatan `callout`, edisi Indonesianya juga punya lima. Pembaca Indonesia tidak sedang membaca versi ringan.

**Istilah teknis tetap dalam bahasa Inggris.** Ini keputusan sadar dan dijelaskan di bagian berikutnya.

## Istilah yang dipertahankan dalam bahasa Inggris

Memaksakan padanan Indonesia untuk istilah yang sehari hari memang diucapkan dalam bahasa Inggris justru membuat teks lebih sulit dibaca, bukan lebih mudah. Seorang analis di KLHK atau di NGO konservasi mengatakan "cloud masking", bukan "pemulihan awan". Kalau buku ini memakai istilah yang tidak dipakai siapa pun, pembaca harus menerjemahkan balik di kepalanya sebelum bisa memakainya.

| Tetap Inggris | Bukan |
|---|---|
| cloud masking | pemulihan awan, penyamaran awan |
| composite | citra gabungan |
| band | saluran |
| feature stack | tumpukan fitur |
| classifier | pengklasifikasi |
| Random Forest, SVM, gradient tree boost | (nama algoritma tidak diterjemahkan) |
| reducer | peringkas |
| server side, client side | sisi server, sisi klien (boleh, tapi istilah Inggris lebih lazim) |
| backscatter | hamburan balik (boleh pada penjelasan pertama, lalu backscatter) |
| speckle | bintik |
| overfitting | (tidak ada padanan yang dipakai) |
| data leakage | kebocoran data (boleh pada penjelasan pertama) |
| confusion matrix | matriks kekeliruan (boleh pada penjelasan pertama) |
| producer accuracy, user accuracy | akurasi produsen, akurasi pengguna (keduanya lazim, pakai konsisten) |
| minimum mapping unit | unit pemetaan minimum (boleh, sebutkan singkatannya) |
| embedding | (tidak diterjemahkan) |
| threshold | ambang batas (boleh, keduanya lazim) |
| export, asset, script, repository | (istilah antarmuka Earth Engine, jangan diterjemahkan) |
| low shot learning | (tidak diterjemahkan) |
| stratified sampling | sampling terstratifikasi |
| cross validation | validasi silang (lazim di literatur Indonesia) |

Pola yang dipakai: **istilah Inggris pada penyebutan pertama, dengan penjelasan singkat dalam bahasa Indonesia, lalu istilah Inggris seterusnya.** Contoh:

> Speckle, bintik multiplikatif yang melekat pada pencitraan koheren, harus difilter sebelum data radar dipakai. Filter speckle yang dipilih di sini adalah focal median.

## Istilah yang memang wajar diterjemahkan

Sebagian istilah sudah lama punya padanan Indonesia yang benar benar dipakai orang. Untuk yang ini, pakai bahasa Indonesia.

piksel, resolusi spasial, resolusi temporal, resolusi spektral, resolusi radiometrik, tutupan lahan, penginderaan jauh, citra satelit, klasifikasi terbimbing, akurasi keseluruhan, data latih, data validasi, elevasi, kemiringan lereng, tanda tangan spektral, koreksi atmosfer, reflektansi permukaan, pasang surut, tajuk, biomassa.

## Gaya penulisan

Aturan berikut diambil dari `academic-humaniser`, Bagian B dan D, dan disesuaikan untuk bahasa Indonesia.

**Jangan pakai tanda pisah sebagai tanda baca kalimat.** Tidak ada em dash, tidak ada en dash sebagai penyela. Pakai koma, titik koma, titik dua, titik, atau kurung.

**Hindari kosakata yang menandakan tulisan mesin.** Dalam bahasa Indonesia, tanda tandanya berbeda dari bahasa Inggris tetapi polanya sama: *krusial*, *signifikan* yang dipakai berulang, *menyoroti*, *mencerminkan*, *memainkan peran penting*, *menjadi bukti nyata*, *lanskap* dalam arti abstrak, *tak hanya ... tetapi juga* sebagai penopang retoris. Ganti dengan kalimat yang menyatakan hal konkret.

Sebelum:
> Mangrove memainkan peran krusial dalam ekosistem pesisir, mencerminkan hubungan mendalam antara masyarakat dan lingkungannya.

Sesudah:
> Mangrove menyimpan tiga sampai empat kali lebih banyak karbon per hektar dibanding hutan tropis daratan, dan sekitar 87 persen di antaranya berada di tanah, bukan di pohonnya.

**Jangan memaksakan tiga.** Kalau ada dua hal yang perlu disebut, sebutkan dua. Menambahkan yang ketiga hanya supaya terdengar lengkap adalah tanda tulisan mesin.

**Variasikan panjang kalimat.** Kalimat pendek di antara kalimat panjang. Paragraf yang semuanya sama panjang terbaca datar.

**Nyatakan klaim secara langsung.** Hindari menumpuk kata pengaman: *mungkin dapat berpotensi menjadi*. Satu kata pengaman cukup.

**Jangan mengembang.** "Perlu dicatat bahwa data menunjukkan" cukup ditulis "data menunjukkan". "Dalam rangka untuk" cukup "untuk".

## Yang tidak boleh berubah dalam terjemahan

- Angka, satuan, dan rentang. 41.200 hektar tetap 41.200 hektar.
- Nama dataset dan ID Earth Engine. `COPERNICUS/S2_SR_HARMONIZED` tidak diterjemahkan dan tidak diubah kapitalisasinya.
- Kode. Nama variabel, nama fungsi, dan nama band tetap seperti aslinya.
- Peringatan teknis. Kalau naskah Inggris memperingatkan bahwa `updateMask` berbeda dari mengisi nol, edisi Indonesia harus memuat peringatan yang sama, sekuat itu.
- Judul `callout`. Konsep, Kesalahan umum, Integritas ilmiah, Dari lapangan. Pakai keempatnya secara konsisten.

## Format angka

Bahasa Indonesia memakai koma sebagai pemisah desimal dan titik sebagai pemisah ribuan. 0,84 bukan 0.84. 41.200 bukan 41,200.

Pengecualian: di dalam kode dan di dalam nilai yang disalin dari keluaran Earth Engine, biarkan format aslinya, karena itulah yang akan dilihat pembaca di layar.

## Cara kerja

1. Baca bab Inggrisnya sampai selesai sebelum menerjemahkan apa pun. Terjemahan paragraf demi paragraf kehilangan alur argumennya.
2. Tulis ulang dalam bahasa Indonesia, bukan menerjemahkan kalimat per kalimat.
3. Periksa: apakah semua `callout` ikut? Semua angka? Semua peringatan?
4. Baca keras keras. Kalau ada kalimat yang tidak akan Anda ucapkan saat menjelaskan ke rekan kerja, tulis ulang.
