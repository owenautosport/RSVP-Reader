// RSVP Pocket Reader — Phase B+: filled-box highlight, faster/adjustable animation,
// gliding menu box, scrollable paragraph. LCDwiki 2.8" ESP32-S3 (ILI9341, FT6336).

#include <Arduino.h>
#include <Arduino_GFX_Library.h>
#include <Preferences.h>
#include <SD_MMC.h>
#include <map>
#include "fonts/FreeSans9pt7b.h"
#include "fonts/FreeSans12pt7b.h"
#include "fonts/FreeSans18pt7b.h"
#include "fonts/FreeSansBold12pt7b.h"
#include "fonts/FreeSansBold18pt7b.h"
#include "fonts/FreeSansBold24pt7b.h"
#include "tokenizer.h"
#include "pivot.h"
#include "RsvpEngine.h"
#include "Navigator.h"
#include "Ft6336.h"

#define TFT_CS 10
#define TFT_DC 46
#define TFT_SCK 12
#define TFT_MOSI 11
#define TFT_MISO 13
#define TFT_RST -1
#define TFT_BL 45
#define TP_SDA 16
#define TP_SCL 15
#define TP_RST 18

#define C_BG    RGB565(0x00, 0x00, 0x00)
#define C_FG    RGB565(0xf2, 0xf2, 0xf2)
#define C_DIM   RGB565(0x66, 0x66, 0x66)
#define C_PIVOT RGB565(0xff, 0x7a, 0x33)
#define C_GUIDE RGB565(0x33, 0x33, 0x33)

#define PIVOT_RELX 0.45f
#define STATUS_H 22
#define MENU_ROW_H 36
#define SPI_HZ 80000000

Arduino_DataBus *bus = new Arduino_ESP32SPI(TFT_DC, TFT_CS, TFT_SCK, TFT_MOSI, TFT_MISO);
Arduino_GFX *output = new Arduino_ILI9341(bus, TFT_RST, 1, true);
Arduino_Canvas *canvas = new Arduino_Canvas(320, 240, output);
Arduino_GFX *gfx = canvas;
Ft6336 touch(TP_SDA, TP_SCL, TP_RST);

RsvpEngine engine;
std::string g_title = "Sample";                        // current book title (status line)
struct Chapter { int idx; std::string title; };
std::vector<Chapter> g_chapters;
std::string g_posKey = "pos";                          // NVS key for this book's position
bool g_sdOk = false;
uint32_t lastTick = 0, holdMs = 200;

static const char *SAMPLE =
    "The quick brown fox jumps over the lazy dog. Reading one word at a time, "
    "centered, lets your eyes stay still while the words come to you. This is "
    "rapid serial visual presentation, running on the little screen in your hand. "
    "Tap to start or stop, swipe up or down to change speed, swipe right for the "
    "menu, and swipe left to read it as a paragraph. Swiping up and down here "
    "scrolls the whole text, and tapping any word jumps the reader to it.";
int W, H;
bool paragraph = false;
int g_paraScroll = 0, g_paraContentH = 0, g_curWordAbsY = 0;
float g_scrollVel = 0, g_dragVel = 0;                  // momentum (phone-like flick scroll)
uint16_t *g_oldbuf = nullptr, *g_compbuf = nullptr;

// animation speed (adjustable in Settings)
int g_animLevel = 1;                                   // default Fast
const char *ANIM_NAMES[] = {"Instant", "Fast", "Smooth"};
const int ANIM_SLIDE[] = {1, 6, 12};
const int ANIM_MENU[]  = {1, 4, 8};
int slideSteps() { return ANIM_SLIDE[g_animLevel]; }
int menuSteps()  { return ANIM_MENU[g_animLevel]; }

// persisted settings + reading position (NVS flash)
Preferences prefs;
bool g_orp = true;                                     // ORP pivot highlight on/off
int g_brightLevel = 9;                                 // backlight level index (10% steps)
const int BRIGHT_PCT[] = {10, 20, 30, 40, 50, 60, 70, 80, 90, 100};
const int BRIGHT_N = 10;

// battery + auto-off (Phase E)
#define BAT_ADC 9
int g_battPct = -1;                                    // -1 = no battery / USB only
const char *AUTOOFF_NAMES[] = {"Never", "1 min", "5 min", "15 min"};
const int AUTOOFF_MIN[] = {0, 1, 5, 15};
int g_autoOffIdx = 0;
uint32_t g_lastActivity = 0;
bool g_sleeping = false, g_swallow = false;

std::vector<uint16_t> g_wordW;                          // cached paragraph word pixel widths
void buildWordWidths();
// caps so a malformed/huge .rsvp can't exhaust memory or hang the device
static const size_t MAX_WORDS = 120000;
static const size_t MAX_WORD_LEN = 48;
static const int MAX_CHAPTERS = 2000;
static const int MAX_HEADER_LINES = 6000;
static const int MAX_LINE_LEN = 512;
static const int MAX_LIBRARY = 200;

void applyBrightness() { ledcWrite(TFT_BL, BRIGHT_PCT[g_brightLevel] * 255 / 100); }

// battery: read GPIO9 (assume 2:1 divider); -1 if no/implausible cell (USB only)
int batteryRead() {
    uint32_t mv = (uint32_t)analogReadMilliVolts(BAT_ADC) * 2;
    if (mv < 2700 || mv > 4400) return -1;     // below ~2.7V there's effectively no usable cell
    int pct = ((int)mv - 3300) * 100 / 900;
    return pct < 0 ? 0 : (pct > 100 ? 100 : pct);
}
void drawBatteryIcon(int x, int y, int pct) {
    const int w = 30, h = 14;
    uint16_t col = (pct <= 20) ? RGB565(0xff, 0x3b, 0x30) : C_PIVOT;
    gfx->drawRect(x, y, w, h, C_DIM);
    gfx->fillRect(x + w, y + 4, 2, 6, C_DIM);            // terminal nub
    int fillw = pct * (w - 4) / 100;
    if (fillw > 0) gfx->fillRect(x + 2, y + 2, fillw, h - 4, col);
    // percentage on top, like iPhone (built-in 6x8 font fits)
    gfx->setFont(NULL);
    gfx->setTextSize(1);
    gfx->setTextColor(C_FG);
    char b[5]; snprintf(b, sizeof(b), "%d", pct);
    int tw = (int)strlen(b) * 6;
    gfx->setCursor(x + (w - tw) / 2, y + (h - 8) / 2);
    gfx->print(b);
}
void sleepNow() { g_sleeping = true; ledcWrite(TFT_BL, 0); }   // backlight off
void wakeUp()   { g_sleeping = false; applyBrightness(); }     // panel content is retained

void loadSettings() {
    prefs.begin("rsvp", true);
    engine.setWpm(prefs.getInt("wpm", 300));
    g_orp = prefs.getBool("orp", true);
    g_brightLevel = prefs.getInt("bright", 9);
    g_animLevel = prefs.getInt("anim", 1);
    g_autoOffIdx = prefs.getInt("aoff", 0);
    prefs.end();
    if (g_brightLevel < 0 || g_brightLevel >= BRIGHT_N) g_brightLevel = 9;
    if (g_animLevel < 0 || g_animLevel > 2) g_animLevel = 1;
    if (g_autoOffIdx < 0 || g_autoOffIdx > 3) g_autoOffIdx = 0;
}
void saveSettings() {
    prefs.begin("rsvp", false);
    prefs.putInt("wpm", engine.wpm());
    prefs.putBool("orp", g_orp);
    prefs.putInt("bright", g_brightLevel);
    prefs.putInt("anim", g_animLevel);
    prefs.putInt("aoff", g_autoOffIdx);
    prefs.end();
}
void savePos() { prefs.begin("rsvp", false); prefs.putInt(g_posKey.c_str(), engine.index()); prefs.end(); }
int loadPos() { prefs.begin("rsvp", true); int p = prefs.getInt(g_posKey.c_str(), 0); prefs.end(); return p; }

// ---------- books from microSD (.rsvp) ----------
std::string posKeyFor(const std::string &name) {           // short, NVS-safe per-book key
    uint32_t h = 2166136261u;
    for (char c : name) { h ^= (uint8_t)c; h *= 16777619u; }
    char k[12]; snprintf(k, sizeof(k), "p%08x", (unsigned)h);
    return std::string(k);
}
bool sdBegin() {
    SD_MMC.setPins(38, 40, 39, 41, 48, 47);                // CLK,CMD,D0,D1,D2,D3
    if (SD_MMC.begin("/sdcard", false)) return true;        // 4-bit
    SD_MMC.setPins(38, 40, 39);
    return SD_MMC.begin("/sdcard", true);                   // 1-bit fallback
}
// read one line up to '\n'/EOF, but never more than MAX_LINE_LEN chars (extra discarded)
String readLineCapped(File &f) {
    String s;
    while (f.available()) {
        int c = f.read();
        if (c < 0 || c == '\n') break;
        if ((int)s.length() < MAX_LINE_LEN) s += (char)c;   // bounded; rest of an over-long line is dropped
    }
    return s;
}
// device-side tokenize with hard caps on count and per-word length (untrusted input)
std::vector<std::string> tokenizeCapped(const std::string &text) {
    std::vector<std::string> w;
    size_t i = 0, n = text.size();
    while (i < n && w.size() < MAX_WORDS) {
        while (i < n && (unsigned char)text[i] <= ' ') i++;
        size_t s = i;
        while (i < n && (unsigned char)text[i] > ' ') i++;
        if (i > s) { size_t len = i - s; if (len > MAX_WORD_LEN) len = MAX_WORD_LEN; w.push_back(text.substr(s, len)); }
    }
    return w;
}

std::string readTitle(const std::string &path) {
    File f = SD_MMC.open(path.c_str()); if (!f) return "";
    std::string title;
    for (int i = 0; i < 50 && f.available(); i++) {
        String ln = readLineCapped(f); ln.trim();
        if (ln == "B") break;
        if (ln.startsWith("T\t")) { title = ln.substring(2).c_str(); break; }
    }
    f.close(); return title;
}
void resetReader(const std::string &title, const std::string &key) {
    g_title = title.empty() ? "Book" : title;
    g_posKey = key;
    int p = loadPos();
    if (p > 0 && p < engine.totalWords()) engine.seekTo(p);
    engine.pause();
}
void loadSample() {
    engine.load(tokenizeCapped(SAMPLE));
    g_chapters.clear();
    buildWordWidths();
    resetReader("Sample", "pos");
}
bool loadBookFromSD(const std::string &path) {
    File f = SD_MMC.open(path.c_str()); if (!f) return false;
    g_chapters.clear();
    std::string title;
    int headerLines = 0;
    while (f.available() && headerLines++ < MAX_HEADER_LINES) {   // header lines up to "B" (bounded)
        String t = readLineCapped(f); t.trim();
        if (t == "RSVP1" || t.length() == 0) continue;
        if (t == "B") break;
        if (t.startsWith("T\t")) title = t.substring(2).c_str();
        else if (t.startsWith("C\t") && (int)g_chapters.size() < MAX_CHAPTERS) {
            int a = t.indexOf('\t'), b = t.indexOf('\t', a + 1);
            if (b > 0) g_chapters.push_back({(int)t.substring(a + 1, b).toInt(), std::string(t.substring(b + 1).c_str())});
        }
    }
    std::string body;
    const size_t CAP = 2 * 1024 * 1024;
    uint8_t buf[2048];
    while (f.available() && body.size() < CAP) {
        int n = f.read(buf, sizeof(buf)); if (n <= 0) break;
        body.append((char *)buf, n);
    }
    f.close();
    engine.load(tokenizeCapped(body));
    body.clear(); body.shrink_to_fit();                          // free the body before building widths
    buildWordWidths();
    resetReader(title, posKeyFor(path));
    Serial.printf("[RSVP] loaded %s: %d words, %d chapters\n", path.c_str(), engine.totalWords(), (int)g_chapters.size());
    return engine.totalWords() > 0;
}

std::vector<MenuItem> buildLibraryItems() {
    std::vector<MenuItem> items;
    items.push_back(MenuItem("b:sample", "Sample (built-in)"));
    if (g_sdOk) {
        File root = SD_MMC.open("/");
        if (root) {
            int count = 0;
            for (File e = root.openNextFile(); e && count < MAX_LIBRARY; e = root.openNextFile()) {
                count++;
                std::string n = e.name();
                size_t sl = n.find_last_of('/'); std::string base = (sl == std::string::npos) ? n : n.substr(sl + 1);
                if (!e.isDirectory() && base.size() > 5 && base.substr(base.size() - 5) == ".rsvp") {
                    std::string path = "/" + base;
                    std::string title = readTitle(path); if (title.empty()) title = base;
                    items.push_back(MenuItem("f:" + path, title));
                }
                e.close();
            }
            root.close();
        }
    } else {
        items.push_back(MenuItem("nosd", "(no SD card)", false));
    }
    items.push_back(MenuItem("back", "Back"));
    return items;
}
std::vector<MenuItem> buildChapterItems() {
    std::vector<MenuItem> items;
    if (g_chapters.empty()) items.push_back(MenuItem("none", "(no chapters)", false));
    else for (auto &c : g_chapters) { char id[16]; snprintf(id, sizeof(id), "%d", c.idx); items.push_back(MenuItem(id, c.title)); }
    items.push_back(MenuItem("back", "Back"));
    return items;
}

struct WordHit { int x, y, w, h, idx; };
std::vector<WordHit> g_paraHits;

std::map<Screen, Menu> g_menus = {
    {Screen::Menu, Menu({MenuItem("resume", "Resume"), MenuItem("library", "Library"),
                         MenuItem("chapters", "Chapters"), MenuItem("settings", "Settings"),
                         MenuItem("stats", "Stats"), MenuItem("about", "About")})},
    {Screen::Library, Menu()},  {Screen::Chapters, Menu()},
    {Screen::Settings, Menu()}, {Screen::Stats, Menu()}, {Screen::About, Menu()},
};
Navigator nav(g_menus);

void drawRoundOutline(int x, int y, int w, int h, int r, uint16_t c) {
    gfx->drawRoundRect(x, y, w, h, r, c);
    gfx->drawRoundRect(x + 1, y + 1, w - 2, h - 2, r - 1, c);
}

// ---------- reading ----------
const GFXfont *pickWordFont(const std::string &w) {
    const GFXfont *fonts[] = {&FreeSansBold24pt7b, &FreeSansBold18pt7b, &FreeSansBold12pt7b};
    for (int i = 0; i < 3; i++) {
        gfx->setFont(fonts[i]);
        int16_t bx, by; uint16_t bw, bh;
        gfx->getTextBounds(w.c_str(), 0, 0, &bx, &by, &bw, &bh);
        if ((int)bw <= W - 16) return fonts[i];
    }
    return &FreeSansBold12pt7b;
}

void drawReadingCanvas() {
    gfx->fillScreen(C_BG);
    gfx->setFont(&FreeSans9pt7b);
    gfx->setTextColor(C_DIM);
    gfx->setCursor(4, 15);
    gfx->print(g_title.c_str());
    int rightX = W - 4;
    if (g_battPct >= 0) { drawBatteryIcon(W - 36, 3, g_battPct); rightX = W - 42; }
    char r[28];
    snprintf(r, sizeof(r), "%d%%  %d wpm %s", (int)(engine.progress() * 100),
             engine.wpm(), engine.isPlaying() ? ">" : "||");
    gfx->setFont(&FreeSans9pt7b);                       // reset (battery icon used the small font)
    gfx->setTextColor(C_DIM);
    int16_t bx, by; uint16_t bw, bh;
    gfx->getTextBounds(r, 0, 0, &bx, &by, &bw, &bh);
    gfx->setCursor(rightX - (int)bw, 15);
    gfx->print(r);

    std::string w = engine.currentWord();
    if (w.empty()) return;
    int cy = STATUS_H + (H - STATUS_H) / 2;
    gfx->setFont(pickWordFont(w));
    gfx->getTextBounds(w.c_str(), 0, 0, &bx, &by, &bw, &bh);
    int baseline = cy - (int)bh / 2 - by;
    if (!g_orp) {                              // pivot off: plain centred word
        gfx->setTextColor(C_FG);
        gfx->setCursor((W - (int)bw) / 2 - bx, baseline);
        gfx->print(w.c_str());
        return;
    }
    int p = pivotIndex(w);
    std::string before = w.substr(0, p), pv = w.substr(p, 1);
    int16_t pbx, pby; uint16_t pbw, pbh, cpw, cph;
    gfx->getTextBounds(before.c_str(), 0, 0, &pbx, &pby, &pbw, &pbh);
    gfx->getTextBounds(pv.c_str(), 0, 0, &pbx, &pby, &cpw, &cph);
    int pivotX = (int)(W * PIVOT_RELX);
    int startX = pivotX - (int)pbw - (int)cpw / 2;
    gfx->fillRect(pivotX - 1, cy - (int)bh, 2, (int)(bh * 0.45f), C_GUIDE);
    gfx->fillRect(pivotX - 1, cy + (int)(bh * 0.55f), 2, (int)(bh * 0.45f), C_GUIDE);
    gfx->setCursor(startX, baseline);
    for (size_t i = 0; i < w.size(); i++) {
        gfx->setTextColor((int)i == p ? C_PIVOT : C_FG);
        gfx->print(w[i]);
    }
}

// ---------- menu (filled orange box, dark text, gliding) ----------
int menuStartY(int n) { int s = (H - n * MENU_ROW_H) / 2; return s < 2 ? 2 : s; }
int menuRowCenter(int n, int i) { return menuStartY(n) + i * MENU_ROW_H + MENU_ROW_H / 2; }

void menuItemBox(Menu &m, int i, int &bx, int &by, int &bw, int &bh) {
    gfx->setFont(&FreeSansBold12pt7b);
    int16_t gx, gy; uint16_t gw, gh;
    gfx->getTextBounds(m.items()[i].label.c_str(), 0, 0, &gx, &gy, &gw, &gh);
    int padX = 16, h = MENU_ROW_H - 6, n = (int)m.items().size();
    bw = (int)gw + 2 * padX; bh = h; bx = (W - bw) / 2;
    by = menuRowCenter(n, i) - h / 2;
}

void drawMenuFrame(Menu &m, int boxCenterY, int boxW, int boxH, int activeIdx) {
    gfx->fillScreen(C_BG);
    gfx->setFont(&FreeSansBold12pt7b);
    int n = (int)m.items().size(), sy = menuStartY(n);
    for (int i = 0; i < n; i++) {
        if (i == activeIdx) continue;
        const std::string &label = m.items()[i].label;
        int16_t gx, gy; uint16_t gw, gh;
        gfx->getTextBounds(label.c_str(), 0, 0, &gx, &gy, &gw, &gh);
        gfx->setTextColor(C_FG);
        gfx->setCursor((W - (int)gw) / 2 - gx, sy + i * MENU_ROW_H + MENU_ROW_H / 2 - (int)gh / 2 - gy);
        gfx->print(label.c_str());
    }
    gfx->fillRoundRect((W - boxW) / 2, boxCenterY - boxH / 2, boxW, boxH, 10, C_PIVOT);
    if (activeIdx >= 0 && activeIdx < n) {
        const std::string &label = m.items()[activeIdx].label;
        int16_t gx, gy; uint16_t gw, gh;
        gfx->getTextBounds(label.c_str(), 0, 0, &gx, &gy, &gw, &gh);
        gfx->setTextColor(C_BG);                                   // dark text inside the box
        gfx->setCursor((W - (int)gw) / 2 - gx, boxCenterY - (int)gh / 2 - gy);
        gfx->print(label.c_str());
    }
}

void drawMenuCanvas(Menu &m) {
    int bx, by, bw, bh; menuItemBox(m, m.index(), bx, by, bw, bh);
    drawMenuFrame(m, by + bh / 2, bw, bh, m.index());
}

void animateMenuBox(Menu &m, int oldIdx, int newIdx) {
    int ox, oy, ow, oh; menuItemBox(m, oldIdx, ox, oy, ow, oh);
    int nx, ny, nw, nh; menuItemBox(m, newIdx, nx, ny, nw, nh);
    int N = menuSteps(); if (N < 1) N = 1;
    int n = (int)m.items().size();
    for (int s = 1; s <= N; s++) {
        float t = (float)s / N;
        int cy = (oy + oh / 2) + (int)(((ny + nh / 2) - (oy + oh / 2)) * t);
        int bw = ow + (int)((nw - ow) * t);
        int active = newIdx, best = 100000;
        for (int i = 0; i < n; i++) { int d = abs(menuRowCenter(n, i) - cy); if (d < best) { best = d; active = i; } }
        drawMenuFrame(m, cy, bw, nh, active);
        gfx->flush();
    }
}

// ---------- info ----------
void drawInfoCanvas(Screen s) {
    gfx->fillScreen(C_BG);
    const char *title = "";
    std::vector<std::string> lines;
    char b[48];
    if (s == Screen::Stats) {
        title = "Stats";
        if (engine.totalWords() > 0) {
            snprintf(b, sizeof(b), "%d%% read", (int)(engine.progress() * 100)); lines.push_back(b);
            snprintf(b, sizeof(b), "%d / %d words", engine.index() + 1, engine.totalWords()); lines.push_back(b);
            snprintf(b, sizeof(b), "%d wpm", engine.wpm()); lines.push_back(b);
        } else lines.push_back("No book open");
    } else if (s == Screen::About) {
        title = "About"; lines.push_back("RSVP Pocket Reader"); lines.push_back("device build");
        snprintf(b, sizeof(b), "%d words loaded", engine.totalWords()); lines.push_back(b);
    } else if (s == Screen::Library) {
        title = "Library"; lines.push_back("Books load from SD"); lines.push_back("(coming in Phase D)");
    } else if (s == Screen::Chapters) {
        title = "Chapters"; lines.push_back("Chapter list"); lines.push_back("(coming in Phase D)");
    }
    gfx->setFont(&FreeSansBold18pt7b);
    gfx->setTextColor(C_FG);
    int16_t bx, by; uint16_t bw, bh;
    gfx->getTextBounds(title, 0, 0, &bx, &by, &bw, &bh);
    gfx->setCursor((W - (int)bw) / 2 - bx, (int)(H * 0.26));
    gfx->print(title);
    gfx->setFont(&FreeSans9pt7b);
    int y = (int)(H * 0.45);
    for (size_t i = 0; i < lines.size(); i++) {
        gfx->setTextColor(i == lines.size() - 1 ? C_DIM : C_FG);
        gfx->getTextBounds(lines[i].c_str(), 0, 0, &bx, &by, &bw, &bh);
        gfx->setCursor((W - (int)bw) / 2 - bx, y);
        gfx->print(lines[i].c_str());
        y += 22;
    }
}

// precompute paragraph word widths once per book (avoids per-frame getTextBounds while scrolling)
void buildWordWidths() {
    g_wordW.clear();
    const auto &ws = engine.words();
    g_wordW.reserve(ws.size());
    gfx->setFont(&FreeSans18pt7b);
    int16_t bx, by; uint16_t bw, bh;
    for (const auto &wd : ws) { gfx->getTextBounds(wd.c_str(), 0, 0, &bx, &by, &bw, &bh); g_wordW.push_back(bw); }
}

// ---------- paragraph (scrollable; current word = filled orange box, dark text) ----------
void buildParagraph(bool draw) {
    if (draw) gfx->fillScreen(C_BG);
    gfx->setFont(&FreeSans18pt7b);
    if (draw) g_paraHits.clear();
    const auto &ws = engine.words();
    int cur = engine.index();
    int margin = 8, x = margin, lineH = 36, spaceW = 7, absY = 28;
    const int boxH = 30;                       // uniform box, < lineH so it never overlaps the line below
    bool haveW = g_wordW.size() == ws.size();
    for (size_t i = 0; i < ws.size(); i++) {
        int gw = haveW ? g_wordW[i] : (int)(ws[i].size() * 10);   // cached width (cheap)
        if (x + gw > W - margin) { x = margin; absY += lineH; }
        if ((int)i == cur) g_curWordAbsY = absY;
        int screenY = absY - g_paraScroll;
        if (draw && screenY > -lineH && screenY < H + lineH) {
            int boxTop = screenY - 23;          // even box centred on the line
            if ((int)i == cur) {
                gfx->fillRoundRect(x - 6, boxTop, gw + 12, boxH, 8, C_PIVOT);
                gfx->setTextColor(C_BG);
            } else gfx->setTextColor(C_FG);
            gfx->setCursor(x, screenY);
            gfx->print(ws[i].c_str());
            g_paraHits.push_back({x - 6, boxTop, gw + spaceW + 12, boxH, (int)i});
        }
        x += gw + spaceW;
    }
    g_paraContentH = absY + lineH;
}

int paraMaxScroll() { int m = g_paraContentH - H + 8; return m < 0 ? 0 : m; }
void clampParaScroll() { if (g_paraScroll < 0) g_paraScroll = 0; if (g_paraScroll > paraMaxScroll()) g_paraScroll = paraMaxScroll(); }
int wordAt(int px, int py) {
    for (const auto &h : g_paraHits)
        if (px >= h.x && px < h.x + h.w && py >= h.y && py < h.y + h.h) return h.idx;
    return -1;
}

// ---------- dispatch ----------
bool isMenuScreen() { Menu *m = nav.menu(); return m && !m->items().empty(); }

void drawCurrentScreen() {
    if (paragraph) { buildParagraph(true); return; }
    Screen s = nav.screen();
    if (s == Screen::Reading) drawReadingCanvas();
    else if (isMenuScreen()) drawMenuCanvas(*nav.menu());
    else drawInfoCanvas(s);
}

void setReadingTiming() {
    if (!paragraph && nav.screen() == Screen::Reading) { holdMs = (uint32_t)engine.currentDelayMs(); lastTick = millis(); }
}
void renderScreen() { drawCurrentScreen(); gfx->flush(); setReadingTiming(); }
void showCurrent() { renderScreen(); }

// ---------- sliding transition ----------
void snapshot() { if (g_oldbuf) memcpy(g_oldbuf, canvas->getFramebuffer(), (size_t)W * H * 2); }
void presentSlide(int dir) {
    uint16_t *fbNew = canvas->getFramebuffer();
    if (!g_oldbuf || !g_compbuf) { gfx->flush(); return; }
    int N = slideSteps(); if (N < 1) N = 1;
    for (int step = 1; step <= N; step++) {
        int sx = W * step / N; if (sx < 1) sx = 1; if (sx > W) sx = W;
        for (int r = 0; r < H; r++) {
            uint16_t *dst = g_compbuf + (size_t)r * W, *o = g_oldbuf + (size_t)r * W, *n = fbNew + (size_t)r * W;
            if (dir > 0) { memcpy(dst, o + sx, (W - sx) * 2); memcpy(dst + (W - sx), n, sx * 2); }
            else { memcpy(dst, n + (W - sx), sx * 2); memcpy(dst + sx, o, (W - sx) * 2); }
        }
        output->draw16bitRGBBitmap(0, 0, g_compbuf, W, H);
    }
}
void transitionTo(int dir) { drawCurrentScreen(); presentSlide(dir); setReadingTiming(); }

// ---------- settings ----------
std::vector<MenuItem> buildSettingsItems() {
    char sp[28], pv[28], br[28], an[28], ao[28];
    snprintf(sp, sizeof(sp), "Speed: %d wpm", engine.wpm());
    snprintf(pv, sizeof(pv), "Pivot: %s", g_orp ? "On" : "Off");
    snprintf(br, sizeof(br), "Brightness: %d%%", BRIGHT_PCT[g_brightLevel]);
    snprintf(an, sizeof(an), "Animation: %s", ANIM_NAMES[g_animLevel]);
    snprintf(ao, sizeof(ao), "Auto-off: %s", AUTOOFF_NAMES[g_autoOffIdx]);
    return {MenuItem("set_speed", sp), MenuItem("set_pivot", pv),
            MenuItem("set_bright", br), MenuItem("set_anim", an),
            MenuItem("set_autooff", ao), MenuItem("back", "Back")};
}
// update the navigator's OWN Settings menu in place (keeps the cursor)
void refreshSettingsMenu() {
    Menu *m = nav.menu();
    if (m) { int idx = m->index(); m->setItems(buildSettingsItems()); m->selectIndex(idx); }
}
void cycleSpeed() {                                     // Settings: +50 wpm steps, snapped, wraps 100..1000
    int w = (engine.wpm() / 50) * 50 + 50;
    if (w > 1000) w = 100;
    engine.setWpm(w);
}

void doAct(const std::string &id) {
    if (id == "resume") nav.goReading();
    else if (id == "library") { if (!g_sdOk) g_sdOk = sdBegin(); nav.open(Screen::Library, buildLibraryItems()); }
    else if (id == "chapters") nav.open(Screen::Chapters, buildChapterItems());
    else if (id == "settings") nav.open(Screen::Settings, buildSettingsItems());
    else if (id == "stats") nav.open(Screen::Stats);
    else if (id == "about") nav.open(Screen::About);
}

// ---------- touch ----------
const int TAP_RADIUS = 24, SWIPE_MIN = 40;
bool down = false;
int downX, downY, lastX, lastY;
void mapTouch(uint16_t rx, uint16_t ry, int &sx, int &sy) { sx = ry; sy = 239 - rx; }

void enterParagraph() {
    buildParagraph(false);
    g_paraScroll = g_curWordAbsY - H / 3;
    clampParaScroll();
}

void onRelease() {
    int dx = lastX - downX, dy = lastY - downY;
    bool tap = abs(dx) < TAP_RADIUS && abs(dy) < TAP_RADIUS;
    bool swipe = !tap && (abs(dx) >= SWIPE_MIN || abs(dy) >= SWIPE_MIN);
    if (!tap && !swipe) return;
    bool vert = abs(dy) > abs(dx);
    int backDir = (dx > 0) ? -1 : +1;

    if (paragraph) {
        if (tap) { int idx = wordAt(downX, downY); if (idx >= 0) { engine.seekTo(idx); savePos(); } snapshot(); paragraph = false; transitionTo(-1); }
        else if (!vert) { snapshot(); paragraph = false; transitionTo(-1); }
        else { g_scrollVel = g_dragVel; }      // vertical flick -> momentum
        return;
    }
    Screen s = nav.screen();
    if (s == Screen::Reading) {
        if (tap) { engine.toggle(); savePos(); showCurrent(); }
        else if (vert) { engine.adjustWpm(dy < 0 ? +25 : -25); showCurrent(); }   // persist on leave, not per-swipe (NVS wear)
        else if (dx > 0) { engine.pause(); savePos(); saveSettings(); snapshot(); nav.open(Screen::Menu); transitionTo(-1); }
        else { engine.pause(); savePos(); saveSettings(); snapshot(); paragraph = true; enterParagraph(); transitionTo(+1); }
    } else if (isMenuScreen()) {
        Menu *m = nav.menu();
        if (tap) {
            const MenuItem *c = m->current();
            if (c && c->enabled) {
                std::string id = c->id;
                if (id == "set_anim" || id == "set_speed" || id == "set_pivot" || id == "set_bright" || id == "set_autooff") {
                    if (id == "set_anim") g_animLevel = (g_animLevel + 1) % 3;
                    else if (id == "set_speed") cycleSpeed();
                    else if (id == "set_pivot") g_orp = !g_orp;
                    else if (id == "set_bright") { g_brightLevel = (g_brightLevel + 1) % BRIGHT_N; applyBrightness(); }
                    else if (id == "set_autooff") g_autoOffIdx = (g_autoOffIdx + 1) % 4;
                    saveSettings(); refreshSettingsMenu(); renderScreen();
                }
                else if (id == "back") { snapshot(); nav.back(); transitionTo(-1); }
                else if (nav.screen() == Screen::Library) {
                    if (id == "b:sample") loadSample();
                    else if (id.rfind("f:", 0) == 0) loadBookFromSD(id.substr(2));
                    snapshot(); nav.goReading(); transitionTo(+1);
                }
                else if (nav.screen() == Screen::Chapters) {
                    engine.seekTo(atoi(id.c_str())); savePos();
                    snapshot(); nav.goReading(); transitionTo(+1);
                }
                else { snapshot(); doAct(id); transitionTo(+1); }
            }
        } else if (vert) {
            int oi = m->index(); m->move(dy < 0 ? -1 : +1); int ni = m->index();
            if (ni != oi) animateMenuBox(*m, oi, ni);
        } else { snapshot(); nav.back(); transitionTo(backDir); }
    } else { snapshot(); nav.back(); transitionTo(tap ? -1 : backDir); }
}

void pollTouch() {
    uint16_t rx, ry;
    if (touch.readRaw(rx, ry)) {
        g_lastActivity = millis();
        int sx, sy; mapTouch(rx, ry, sx, sy);
        if (g_sleeping) { wakeUp(); down = true; downX = lastX = sx; downY = lastY = sy; g_swallow = true; return; }
        if (!down) { down = true; downX = lastX = sx; downY = lastY = sy; g_scrollVel = 0; g_dragVel = 0; }
        else {
            if (paragraph && sy != lastY) {
                int d = -(sy - lastY);                 // scroll delta (drag down -> scroll up)
                g_paraScroll += d; clampParaScroll();
                g_dragVel = 0.55f * g_dragVel + 0.45f * d;   // smoothed flick velocity
                buildParagraph(true); gfx->flush();
            }
            lastX = sx; lastY = sy;
        }
    } else if (down) { down = false; if (g_swallow) { g_swallow = false; return; } onRelease(); }
}

void setup() {
    Serial.begin(115200);
    delay(200);
    ledcAttach(TFT_BL, 5000, 8);               // backlight PWM (brightness control)
    gfx->begin(SPI_HZ);
    W = gfx->width(); H = gfx->height();
    size_t sz = (size_t)W * H * 2;
    g_oldbuf = (uint16_t *)ps_malloc(sz);
    g_compbuf = (uint16_t *)heap_caps_malloc(sz, MALLOC_CAP_DMA);
    if (!g_compbuf) g_compbuf = (uint16_t *)ps_malloc(sz);
    touch.begin();

    loadSettings();                            // wpm, orp, brightness, animation from flash
    applyBrightness();
    g_sdOk = sdBegin();                         // mount microSD (SDIO)
    loadSample();                              // default book (sets pos/pause)
    g_battPct = batteryRead();
    g_lastActivity = millis();
    Serial.printf("[RSVP] Phase E: SD=%s, %d words, pos=%d, buf=%s\n",
                  g_sdOk ? "ok" : "none", engine.totalWords(), engine.index(),
                  (g_oldbuf && g_compbuf) ? "ok" : "FAIL");
    renderScreen();
}

void loop() {
    pollTouch();

    // battery poll (~10s) — refresh the icon when reading & idle
    static uint32_t lastBat = 0;
    if (millis() - lastBat > 10000) {
        lastBat = millis();
        int prev = g_battPct; g_battPct = batteryRead();
        if (!g_sleeping && !paragraph && nav.screen() == Screen::Reading && g_battPct != prev) renderScreen();
    }
    // auto-off: sleep when paused + idle past the chosen timeout
    if (!g_sleeping && AUTOOFF_MIN[g_autoOffIdx] > 0 && !engine.isPlaying() &&
        (millis() - g_lastActivity) > (uint32_t)AUTOOFF_MIN[g_autoOffIdx] * 60000UL) {
        sleepNow();
    }
    if (g_sleeping) { delay(20); return; }   // nothing else to do while asleep

    // momentum scroll in the paragraph view (after a flick release)
    if (paragraph && !down && (g_scrollVel > 0.8f || g_scrollVel < -0.8f)) {
        int before = g_paraScroll;
        g_paraScroll += (int)g_scrollVel;
        clampParaScroll();
        if (g_paraScroll == before) g_scrollVel = 0;        // hit a bound
        g_scrollVel *= 0.90f;                               // friction
        buildParagraph(true); gfx->flush();
    }
    if (!paragraph && nav.screen() == Screen::Reading && engine.isPlaying() &&
        (millis() - lastTick) >= holdMs) {
        if (engine.advance()) showCurrent();
        else { engine.pause(); engine.restart(); showCurrent(); }
    }
    delay(5);
}
