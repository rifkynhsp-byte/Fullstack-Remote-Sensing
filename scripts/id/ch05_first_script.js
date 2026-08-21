//| title: Skrip Earth Engine pertama Anda
//| description: Memuat model elevasi global, memeriksanya, dan menggambarnya di peta.

/**
 * BAB 5 | Skrip Earth Engine pertama Anda
 * ---------------------------------------------------------------------------
 * Tujuan
 *   Menyentuh setiap panel Code Editor satu kali, memakai dataset paling
 *   sederhana yang berguna di katalog: satu citra elevasi global.
 *
 * Yang perlu diperhatikan
 *   Tidak ada satu piksel pun yang diunduh ke laptop Anda. Setiap baris di
 *   bawah menyusun deskripsi pekerjaan. Server Google baru mengerjakannya
 *   ketika peta memerlukan ubin atau Console memerlukan nilai.
 *
 * Diadaptasi dari seri pengajaran EE101 oleh Noel Gorelick, David Gibson,
 * Nicholas Clinton dan Hadi. Tautan repositori ada di bab Rujukan.
 */

// ---------------------------------------------------------------------------
// 1. Muat satu citra dari katalog publik
// ---------------------------------------------------------------------------
// CGIAR/SRTM90_V4 adalah satu citra yang menutup seluruh planet: model
// elevasi Shuttle Radar Topography Mission, disampel ulang ke sekitar 90 m.
//
// Ada dua jalan menuju objek yang sama. Anda dapat mencari "SRTM" di bilah
// katalog, klik Import, lalu ganti nama variabelnya di blok Imports di bagian
// atas editor. Atau Anda menyebut ID asetnya langsung, seperti di bawah.
// Cara kedua lebih disukai dalam buku, karena skripnya mandiri dan tetap
// jalan ketika disalin antar akun.
var dem = ee.Image('CGIAR/SRTM90_V4');

// ---------------------------------------------------------------------------
// 2. Tanyakan kepada server apa yang sedang dipegangnya
// ---------------------------------------------------------------------------
// print() mengirim permintaan ke Earth Engine dan menulis balasannya ke tab
// Console di sebelah kanan. Bentangkan hasilnya untuk melihat daftar band,
// tipe data, jejak piksel dan properti metadata. Membaca balasan ini dengan
// cermat adalah kebiasaan yang mencegah sebagian besar galat berikutnya: nama
// band dan tipe data adalah dua hal yang paling sering salah dalam skrip.
print('Objek citra SRTM:', dem);

// ---------------------------------------------------------------------------
// 3. Gambar apa adanya
// ---------------------------------------------------------------------------
// Map.addLayer(eeObject, visParams, name, shown, opacity)
//
//   eeObject  apa yang digambar
//   visParams bagaimana meregangkannya menjadi piksel yang bisa ditampilkan
//   name      label di kontrol Layers, kanan atas peta
//   shown     1 atau true langsung menggambar, 0 atau false membiarkannya mati
//   opacity   0 tak terlihat, 1 pekat
//
// Layer di bawah sengaja ditambahkan dengan shown = 0, sehingga muncul di
// daftar Layers tetapi tetap mati. Menyalakan dan mematikannya adalah cara
// tercepat membandingkan dua cara penggambaran data yang sama.
Map.addLayer(dem.select('elevation'), {min: 0, max: 1200}, 'DEM abu abu', 0, 0.5);

// ---------------------------------------------------------------------------
// 4. Gambar lagi, dengan tangga warna
// ---------------------------------------------------------------------------
// Peregangan skala abu menjawab pertanyaan "setinggi apa", tetapi dengan
// buruk. Palet memetakan rentang angka yang sama ke warna yang jauh lebih
// mudah dipisahkan mata. Entri palet disebar merata sepanjang rentang min
// sampai max.
var elevationPalette = ['blue', 'cyan', 'green', 'yellow', 'red', 'brown'];

var elevationVis = {
  min: 0,               // meter. Muka laut dan di bawahnya dijepit ke warna pertama.
  max: 1200,            // meter. Yang lebih tinggi dijepit ke warna terakhir.
  palette: elevationPalette
};

Map.addLayer(dem.select('elevation'), elevationVis, 'DEM berpalet', 1, 0.5);

// ---------------------------------------------------------------------------
// 5. Arahkan peta ke tempat yang berguna
// ---------------------------------------------------------------------------
// Map.setCenter(bujur, lintang, zoom). Bujur lebih dulu, kebalikan dari
// urutan lintang lebih dulu yang dipakai sebagian besar pustaka peta web dan
// hampir setiap aplikasi GPS. Ini sumber lazim bug "area studi saya ada di
// tengah laut".
//
// Tips: buka tab Inspector, klik di mana pun pada peta, dan panelnya
// melaporkan koordinat serta nilai piksel di bawah kursor. Dari situlah angka
// di bawah ini berasal.
Map.setCenter(117.161, -0.53, 5);   // Kalimantan bagian tengah

// ---------------------------------------------------------------------------
// Latihan
// ---------------------------------------------------------------------------
// 1. Ubah max dari 1200 menjadi 3000 lalu jalankan ulang. Bentang lahan mana
//    yang kehilangan detail, dan mengapa garis pantai jadi lebih sulit dibaca?
// 2. Ganti paletnya dengan tangga dua warna seperti ['white', 'black'].
//    Putuskan versi mana yang lebih baik mengomunikasikan relief kepada orang
//    awam.
// 3. Pakai Inspector untuk menemukan elevasi puncak terdekat dari area studi
//    Anda, lalu atur min dan max agar mengapit nilai itu.
