# AFAD Kıyafet, Ekipman ve Zimmet Yönetimi

81 il ve Başkanlık için personel talebi, onay, depo, sevkiyat ve zimmet süreçlerini yöneten web uygulaması. Python 3.12+ ve SQLite kullanır; harici Python/JavaScript paketi veya internetten yüklenen arayüz bileşeni gerekmez. Veriler tarayıcıda değil sunucuda saklanır.

Bu proje AFAD'ın resmî yayımlanmış yazılımı değildir. Kuruma özel bir uygulama geliştirmesidir.

> **Arayüzü açmak:** Bu GitHub adresi kaynak kod deposudur; çalışan uygulama adresi değildir. Ana sayfa `static/index.html` dosyasındadır ve Python sunucusu tarafından `/` adresinde sunulur. Aşağıdaki kurulumdan sonra `http://127.0.0.1:8000` adresini açın. GitHub Pages yalnız statik dosya yayımlar; bu uygulamanın giriş, API ve veritabanını çalıştıramaz. İnternet üzerinden kullanım için HTTPS sunucu kurulumu gerekir.

## Kıyafet ve ekipman kuralları

- Her personel her **takvim yılında bir yazlık ve bir kışlık takım** talep edebilir. İki takımda da ayakkabı bulunur. Hak ediş yılı Türkiye saat dilimiyle belirlenir.
- Başlangıç yazlık takımı: görev üstü, pantolon, yazlık görev ayakkabısı; her kalemden 1 adet.
- Başlangıç kışlık takımı: mont, görev üstü, pantolon, kışlık görev botu; her kalemden 1 adet. Takımın kesin kalemleri malzeme kataloğunda yönetilebilir.
- **Yıllık Kıyafet Hakkı** ekranı bedene göre takımın eksik kalemlerini tek işlemde talep eder. Kıyafet bedenleri eksikse işlemin tamamı geri alınır.
- Bekleyen normal talepler aynı yılın hakkını rezerve eder. Tamamlanan taleplerde gerçekten teslim edilmiş miktar esas alınır. Ret ve tahsis iptali normal hakkı serbest bırakır. İade, kullanılmış yıllık hakkı yeniden açmaz.
- Hak ediş, talebin oluşturulduğu yıla aittir. Bir önceki yılın açık talebinin sonraki yıl teslim edilmesi yeni yılın hakkını tüketmez. Yıllık hak otomatik **talep veya teslim oluşturmaz**; personel veya yetkili talep açar.
- **KBRN, dağcılık ve diğer özel ekipmanlar ihtiyaç halinde** gerekçeyle talep edilir; yıllık takım sınırına tabi değildir. Personelin uzmanlık alanı inceleme için görüntülenir; uzmanlık uygunluğunu yetkililer değerlendirir.
- Süresinden önce yıpranan malzeme için **Zimmetler → Erken Yıpranma / Yenileme** kullanılır. Teslim onaylı mevcut zimmet ve gerekçe gerekir. Bir zimmete aynı anda bir açık yenileme talebi açılabilir. Yenileme normal yıllık hakkı tüketmez ve onay sürecini atlamaz. Eski zimmet otomatik silinmez; il sorumlusu ayrıca iade alır.
- Hasar, eskime ve kayıp bildirimleri ayrıca kaydedilir.

## GitHub Pages arayüz önizlemesi

Depo kökündeki `index.html` arayüzün statik giriş noktasıdır. GitHub depo adresi dosyaları gösterir; HTML dosyasını uygulama olarak çalıştırmaz.

1. GitHub deposunda **Settings → Pages → Build and deployment → Source: GitHub Actions** seçin.
2. **Actions → Arayüz Önizlemesini Yayınla → Run workflow** çalıştırın.
3. Başarılı yayının ardından **Settings → Pages** ekranındaki ziyaret bağlantısını kullanın. Standart proje adresi `https://afetatlasi.github.io/kiyafet/` olur; bu adres yayının başarılı olduğu doğrulanmadan çalışan bağlantı sayılmaz.

Pages iş akışı yalnız kök ana sayfa, CSS ve JavaScript dosyalarını yayımlar. Kaynak kodu, veritabanı ve diğer sunucu dosyalarını yayın paketine koymaz. Önizlemede giriş alanları kapalıdır ve API çağrısı yapılmaz. Gerçek hesap, talep, stok ve zimmet işlemleri için aşağıdaki Python sunucu kurulumunu kullanın. Üretim sunucusu `static/index.html` dosyasını sunmaya devam eder.

## Kurulum

```bash
git clone https://github.com/afetatlasi/kiyafet.git
cd kiyafet
python3 --version  # 3.12 veya üzeri
python3 server.py --init-admin
python3 server.py
```

`http://127.0.0.1:8000` adresini açın. İlk komut yönetici kullanıcı adı ve parolasını etkileşimli ister. Parola en az 12 karakter olmalıdır; **varsayılan veya kaynak kodda kayıtlı parola yoktur**. Windows'ta `python3` yerine `python` kullanılabilir. Veritabanı ilk çalıştırmada `data/afad.sqlite3` altında oluşturulur. Uygulama dizininden bağımsız başlatılabilir.

Yönetici önce il malzeme sorumlusu, il müdürü, Başkanlık ve personel hesaplarını oluşturur; personel giriş yapıp bedenlerini kaydeder. Sistemde gerçek personel ve stok kaydı başlangıçta bulunmaz. İl ve örnek malzeme tanımları otomatik oluşturulur.

```bash
python3 server.py --db /guvenli-dizin/afad.sqlite3 --init-admin
python3 server.py --db /guvenli-dizin/afad.sqlite3 --port 8000
```

`AFAD_DB` veritabanı yolunu, `AFAD_ORIGIN` tarayıcının kullandığı kök adresi belirleyebilir. Parolaları komut satırı argümanlarına veya depoya yazmayın.

## Roller

| Rol | Yetki |
| --- | --- |
| Personel | Kendi profil/beden/hak ediş bilgileri, talepleri, zimmetleri, teslim onayı ve bildirimleri |
| İl Malzeme Sorumlusu | Kendi il personeli, stok, talep incelemesi, doğrudan il stoktan teslim, sevkiyat teslim alma, iade |
| İl Müdürü | Kendi ilinin taleplerine gerekçeli onay/ret ve Başkanlığa tekli/toplu iletim |
| Başkanlık Yetkilisi | 81 ilde inceleme, tam/kısmi tahsis, merkez stok yönetimi ve sevkiyat |
| Sistem Yöneticisi | Kullanıcı/rol/aktiflik, il ataması, birim, katalog, stok ve iş akışı ayarları |

Yönetici lojistik onayları otomatik üstlenmez; il ve Başkanlık onayları ilgili operasyonel rollerle yapılır. Sunucu yetkileri her işlemde kontrol eder; arayüzü değiştirmek veya doğrudan API çağırmak yetki sağlamaz. Aktiflik/rol/parola/il değişikliklerinde kullanıcının açık oturumları kapatılır.

## İş akışı

1. Personel talebi **Malzeme İncelemesinde** başlar.
2. İl sorumlusu kendi stokundan karşılar veya il onayına gönderir.
3. İl müdürü gerekçeyle reddeder veya Başkanlığa iletir. Birden fazla talep seçilip **GRP** numarasıyla toplu iletilebilir.
4. Başkanlık merkez depodaki **aynı beden** stoktan tam/kısmi tahsis yapar veya gerekçeyle reddeder. Tahsis stoktan hemen ayrılır; aynı stok iki talebe verilemez.
5. Sevkiyat referansı girilerek yola çıkarılır. İl sorumlusu teslim aldığında miktar il deposuna eklenir.
6. İl sorumlusu personele teslim eder; zimmet oluşur, il stoğu azalır. Personel kendi hesabından dijital teslim onayı verir. Bu onay nitelikli elektronik imza değildir.
7. İade alınırken zimmet kapatılır ve malzeme güncel il deposuna eklenir. Tüm işlemler kaydedilir.

Kısmi karşılamada eksik miktar görünür; kalan ihtiyaç için yeni talep oluşturulur. Sevk edilmemiş tahsis Başkanlıkça gerekçeyle iptal edilirse merkez stok geri eklenir. İl deposuna ulaşmış veya henüz incelenen talep il sorumlusunca gerekçeyle kapatılabilir; depoya ulaşmış fiziksel malzeme stokta kalır.

İl değişikliğinde zimmet ve teslim geçmişi korunur. Eski talepler oluşturuldukları ilde kalır. Personelin yeni ilindeki sorumlu mevcut zimmetleri görebilir ve iade alabilir. Eski ildeki açık talep yeni ile otomatik taşınmaz; eski talep uygun aşamada kapatılır, gerekirse sevk öncesi tahsis iptal edilir, yeni ilde yeni talep açılır.

## Katalog ve ayarlar

Her malzemede kategori, ölçü birimi, minimum stok, aktiflik, tedarik kuralı (`SUMMER`/`WINTER`/`SPECIAL`), yıllık takım adedi ve beden alanı tanımlıdır. Minimum stok depo ve beden başına uygulanır. Henüz stok kaydı olmayan bir beden stokta yok kabul edilir.

Yönetici şu iş akışı kurallarını değiştirebilir:

- İl stoktan doğrudan teslim açık/kapalı.
- Başkanlığın kısmi tahsisi açık/kapalı.
- Teslimde seri/parti numarası zorunlu/isteğe bağlı.

## Raporlar ve kayıtlar

İhtiyaç, personel, stok, stok hareketi, zimmet/teslim ve hasar/kayıp CSV raporları vardır. Raporlar sunucudaki rol/il/personel kapsamını uygular. Excel formülü olarak çalışabilecek hücreler kaçışlanır. Gösterge değerleri kayıtlı verilerden hesaplanır. Ekrandaki işlem geçmişi ve stok hareketleri son 200 kaydı gösterir. Denetim dahil CSV raporları erişilebilir kayıtların tamamını içerir.

Denetim tablosu uygulama üzerinden eklemeye açıktır, güncelleme/silme SQL tetikleyicileriyle engellenir. Veritabanı dosyasına yönetici erişimi olan kişi bu korumaları değiştirebilir; bu mekanizma kriptografik veya harici değişmez kayıt sistemi değildir.

## Ağda çalıştırma

Kurulum bir uygulama sunucusudur; `http.server` tabanlı HTTP dinleyicisini doğrudan internete açmayın. TLS sonlandıran ters vekil arkasında çalıştırın. Örnek Caddy yapılandırması `deploy/Caddyfile`, sistem servisi `deploy/afad.service` dosyasındadır. Bu örnekler otomatik sunucu kurmaz veya alan adı ayarlamaz.

```bash
python3 server.py --host 127.0.0.1 --port 8000 --origin https://kiyafet.kurum-alaniniz.gov.tr
```

Origin tarayıcı adresiyle birebir eşleşmelidir; HTTP yerine HTTPS origin tanımlanınca çerez `Secure` olur. Sertifika ve DNS'yi kurum altyapısında ayarlayın. Farklı makinedeki ters vekil için özel ağda `--host 0.0.0.0` kullanılabilir; bu durumda HTTPS origin zorunludur ve güvenlik duvarı yalnız ters vekile izin vermelidir. Gerçek işletimde intranet/VPN veya kurumun erişim politikasını uygulayın. Caddy örneği `X-Forwarded-For` başlığını temizler; uygulama istemci IP'si olarak TCP bağlantısını kullanır. Vekil arkasında aynı kullanıcı adına başarısız girişler aynı sınırı paylaşır.

Parolalar scrypt ile tuzlanır; oturum belirteçlerinin yalnız SHA-256 özeti veritabanındadır. Oturum süresi 8 saattir. Çerez HttpOnly/SameSite=Strict, değişiklikler CSRF doğrulamalıdır. CSP ve çıktı kaçışlama kullanılır. 15 dakikada kullanıcı/bağlantı IP'si başına 10 hatalı girişten sonra giriş geçici kilitlenir. MFA/kurum SSO, e-Devlet entegrasyonu, e-imza, e-posta/SMS ve dosya eki bu sürüme dahil değildir.

## Veritabanı ve yedekleme

SQLite WAL ve yazma işlemlerinde `BEGIN IMMEDIATE` kullanılır. Stok, zimmet, durum ve denetim kaydı aynı işlemde yazılır; başarısız işlem geri alınır. Negatif stok ve mükerrer teslim/iade engellenir.

```bash
python3 manage.py backup --output /guvenli-yedek/afad-2026-11-06.sqlite3
python3 manage.py check
```

Veritabanı yolu için her iki komuttan **önce** `--db /yol/afad.sqlite3` ekleyin. Yedekler kişisel veri ve parola özetleri içerir; erişimi sınırlayın, şifreli saklayın ve saklama politikasını kurumunuz belirlesin. Yedek almak sistemi durdurmayı gerektirmez. Geri yükleme için servisi durdurun, mevcut veritabanı ve WAL/SHM dosyalarını güvenli bir yere taşıyın, doğrulanmış yedeği ana veritabanı yoluna kopyalayın, sahiplik ve izinleri düzeltin, `manage.py check` çalıştırıp servisi başlatın. Yedekten dönünce eski oturumların geçerli kalmaması için `python3 manage.py invalidate-sessions` çalıştırın.

Bu sürüm tek uygulama sunucusu ve yerel SQLite diskiyle çalışır; veritabanını NFS/paylaşımlı ağ diskine koymayın. 81 il tanımı desteklenir; 81 ilin eşzamanlı gerçek kullanım yükü ölçülmüş değildir. Çoklu sunucu/yoğun trafik için PostgreSQL ve üretim uygulama sunucusuna geçiş, kurum ortamında yük/kabul testi gerekir. Kurumsal canlı devreye alma yapılmış değildir.

## Test

```bash
python3 -m unittest discover -s tests -v
node --check static/app.js
node tests/check_frontend.js
```

Testler yıllık hak ve ayakkabı dahil takım talebi, erken yıpranma yenilemesi, KBRN ihtiyacı, takvim yılı değişimi, roller/il sınırı, tam/kısmi sevkiyat, zimmet/iade, eşzamanlı stok çıkışı, gerekçeli ret, toplu talep atomikliği, oturum, CSRF, rapor kapsamı ve CSV kaçışlamasını kapsar. Testler geçici veritabanı kullanır. HTTP testleri localhost soketi açar. GitHub Actions Python testlerini, JavaScript sözdizimini ve 8 hesap üzerinden arayüz oluşturma/form sözleşmesi kontrollerini çalıştırır. Ortamdaki tarayıcı aracı mevcut olmadığından görsel/tarayıcı otomasyonu doğrulaması yapılmamıştır.
