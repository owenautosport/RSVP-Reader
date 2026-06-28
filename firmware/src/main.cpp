// RSVP Pocket Reader — Phase B+: filled-box highlight, faster/adjustable animation,
// gliding menu box, scrollable paragraph. LCDwiki 2.8" ESP32-S3 (ILI9341, FT6336).

#include <Arduino.h>
#include <Arduino_GFX_Library.h>
#include <Preferences.h>
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
const char *BOOK_TITLE = "Sample";
uint32_t lastTick = 0, holdMs = 200;
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
int g_brightLevel = 3;                                 // backlight level index
const int BRIGHT_PCT[] = {20, 45, 70, 100};

void applyBrightness() { ledcWrite(TFT_BL, BRIGHT_PCT[g_brightLevel] * 255 / 100); }

void loadSettings() {
    prefs.begin("rsvp", true);
    engine.setWpm(prefs.getInt("wpm", 300));
    g_orp = prefs.getBool("orp", true);
    g_brightLevel = prefs.getInt("bright", 3);
    g_animLevel = prefs.getInt("anim", 1);
    prefs.end();
    if (g_brightLevel < 0 || g_brightLevel > 3) g_brightLevel = 3;
    if (g_animLevel < 0 || g_animLevel > 2) g_animLevel = 1;
}
void saveSettings() {
    prefs.begin("rsvp", false);
    prefs.putInt("wpm", engine.wpm());
    prefs.putBool("orp", g_orp);
    prefs.putInt("bright", g_brightLevel);
    prefs.putInt("anim", g_animLevel);
    prefs.end();
}
void savePos() { prefs.begin("rsvp", false); prefs.putInt("pos", engine.index()); prefs.end(); }
int loadPos() { prefs.begin("rsvp", true); int p = prefs.getInt("pos", 0); prefs.end(); return p; }

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

static const char *SAMPLE =
    "The quick brown fox jumps over the lazy dog. Reading one word at a time, "
    "centered, lets your eyes stay still while the words come to you. This is "
    "rapid serial visual presentation, running on the little screen in your hand. "
    "Tap to start or stop, swipe up or down to change speed, swipe right for the "
    "menu, and swipe left to read it as a paragraph. Swiping up and down here "
    "scrolls the whole text, and tapping any word jumps the reader to it.";

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
    gfx->print(BOOK_TITLE);
    char r[28];
    snprintf(r, sizeof(r), "%d%%  %d wpm %s", (int)(engine.progress() * 100),
             engine.wpm(), engine.isPlaying() ? ">" : "||");
    int16_t bx, by; uint16_t bw, bh;
    gfx->getTextBounds(r, 0, 0, &bx, &by, &bw, &bh);
    gfx->setCursor(W - (int)bw - 4, 15);
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

// ---------- paragraph (scrollable; current word = filled orange box, dark text) ----------
void buildParagraph(bool draw) {
    if (draw) gfx->fillScreen(C_BG);
    gfx->setFont(&FreeSans18pt7b);
    if (draw) g_paraHits.clear();
    const auto &ws = engine.words();
    int cur = engine.index();
    int margin = 8, x = margin, lineH = 36, spaceW = 7, absY = 28;
    const int boxH = 30;                       // uniform box, < lineH so it never overlaps the line below
    for (size_t i = 0; i < ws.size(); i++) {
        const std::string &wd = ws[i];
        int16_t gx, gy; uint16_t gw, gh;
        gfx->getTextBounds(wd.c_str(), 0, 0, &gx, &gy, &gw, &gh);
        if (x + (int)gw > W - margin) { x = margin; absY += lineH; }
        if ((int)i == cur) g_curWordAbsY = absY;
        int screenY = absY - g_paraScroll;
        if (draw && screenY > -lineH && screenY < H + lineH) {
            int boxTop = screenY - 23;          // even box centred on the line
            if ((int)i == cur) {
                gfx->fillRoundRect(x - 6, boxTop, (int)gw + 12, boxH, 8, C_PIVOT);
                gfx->setTextColor(C_BG);
            } else gfx->setTextColor(C_FG);
            gfx->setCursor(x - gx, screenY);
            gfx->print(wd.c_str());
            g_paraHits.push_back({x - 6, boxTop, (int)gw + spaceW + 12, boxH, (int)i});
        }
        x += (int)gw + spaceW;
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
void refreshSettings() {
    Menu &s = g_menus[Screen::Settings];
    int idx = s.index();
    char sp[28], pv[28], br[28], an[28];
    snprintf(sp, sizeof(sp), "Speed: %d wpm", engine.wpm());
    snprintf(pv, sizeof(pv), "Pivot: %s", g_orp ? "On" : "Off");
    snprintf(br, sizeof(br), "Brightness: %d%%", BRIGHT_PCT[g_brightLevel]);
    snprintf(an, sizeof(an), "Animation: %s", ANIM_NAMES[g_animLevel]);
    s.setItems({MenuItem("set_speed", sp), MenuItem("set_pivot", pv),
                MenuItem("set_bright", br), MenuItem("set_anim", an), MenuItem("back", "Back")});
    s.selectIndex(idx);
}
void cycleSpeed() {
    static const int sp[] = {200, 250, 300, 350, 400, 500}; int n = 6, cur = engine.wpm(), ni = 0, found = -1;
    for (int i = 0; i < n; i++) if (sp[i] == cur) { found = i; break; }
    ni = (found < 0) ? 2 : (found + 1) % n;
    engine.setWpm(sp[ni]);
}

void doAct(const std::string &id) {
    if (id == "resume") nav.goReading();
    else if (id == "library") nav.open(Screen::Library);
    else if (id == "chapters") nav.open(Screen::Chapters);
    else if (id == "settings") { refreshSettings(); nav.open(Screen::Settings); }
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
        else if (vert) { engine.adjustWpm(dy < 0 ? +25 : -25); saveSettings(); showCurrent(); }
        else if (dx > 0) { engine.pause(); savePos(); snapshot(); nav.open(Screen::Menu); transitionTo(-1); }
        else { engine.pause(); savePos(); snapshot(); paragraph = true; enterParagraph(); transitionTo(+1); }
    } else if (isMenuScreen()) {
        Menu *m = nav.menu();
        if (tap) {
            const MenuItem *c = m->current();
            if (c) {
                std::string id = c->id;
                if (id == "set_anim" || id == "set_speed" || id == "set_pivot" || id == "set_bright") {
                    if (id == "set_anim") g_animLevel = (g_animLevel + 1) % 3;
                    else if (id == "set_speed") cycleSpeed();
                    else if (id == "set_pivot") g_orp = !g_orp;
                    else if (id == "set_bright") { g_brightLevel = (g_brightLevel + 1) % 4; applyBrightness(); }
                    saveSettings(); refreshSettings(); renderScreen();
                }
                else if (id == "back") { snapshot(); nav.back(); transitionTo(-1); }
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
        int sx, sy; mapTouch(rx, ry, sx, sy);
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
    } else if (down) { down = false; onRelease(); }
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

    engine.load(tokenize(SAMPLE));
    loadSettings();                            // wpm, orp, brightness, animation from flash
    applyBrightness();
    int p = loadPos();                         // resume reading position
    if (p > 0 && p < engine.totalWords()) engine.seekTo(p);
    engine.pause();                            // start paused — tap to begin
    refreshSettings();
    Serial.printf("[RSVP] Phase C: %d words, pos=%d, buf=%s\n", engine.totalWords(),
                  engine.index(), (g_oldbuf && g_compbuf) ? "ok" : "FAIL");
    renderScreen();
}

void loop() {
    pollTouch();
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
