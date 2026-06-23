// Host-side verification: the C++ Navigator/Menu must behave like the Python
// rsvp/nav. Expected values were captured by running the Python.
//   build: g++ -std=c++17 firmware/test/test_nav.cpp firmware/src/Menu.cpp firmware/src/Navigator.cpp -o /tmp/tn
#include "../src/actions.h"
#include "../src/Menu.h"
#include "../src/Navigator.h"
#include <cstdio>
#include <map>

static int failures = 0;
#define CHECK(cond) do { if(!(cond)){ printf("FAIL %d: %s\n", __LINE__, #cond); failures++; } } while(0)
#define EQS(a,b) do { std::string _a=(a), _b=(b); if(_a!=_b){ \
    printf("FAIL %d: %s == %s  (got '%s' want '%s')\n", __LINE__, #a, #b, _a.c_str(), _b.c_str()); failures++; } } while(0)

int main() {
    std::map<Screen, Menu> menus;
    menus.emplace(Screen::Menu, Menu({MenuItem("resume", "Resume"),
                                      MenuItem("library", "Library"),
                                      MenuItem("settings", "Settings", false)}));
    menus.emplace(Screen::Library, Menu());
    Navigator nav(menus);

    CHECK(!nav.inMenu());
    nav.open(Screen::Menu);
    CHECK(nav.screen() == Screen::Menu); CHECK(nav.inMenu()); CHECK(nav.menu()->index() == 0);
    nav.move(1);  EQS(nav.menu()->current()->id, "library");
    nav.move(1);  EQS(nav.menu()->current()->id, "library");   // skip disabled settings
    EQS(nav.select(), "library");
    nav.move(-1); EQS(nav.menu()->current()->id, "resume");
    nav.menu()->selectIndex(2); EQS(nav.menu()->current()->id, "resume");  // disabled stays

    nav.open(Screen::Library, {MenuItem("/a", "A"), MenuItem("/b", "B")});
    CHECK(nav.screen() == Screen::Library); EQS(nav.menu()->items()[0].id, "/a");
    nav.back(); CHECK(nav.screen() == Screen::Menu);
    nav.back(); CHECK(nav.screen() == Screen::Reading);

    nav.open(Screen::Menu); nav.open(Screen::Library); nav.goReading();
    CHECK(nav.screen() == Screen::Reading);

    Menu m2({MenuItem("x", "X", false), MenuItem("y", "Y")});
    m2.reset(); EQS(m2.current()->id, "y");                     // reset to first enabled

    if (failures == 0) printf("ALL C++ NAV TESTS PASS (matches Python)\n");
    else printf("%d FAILURE(S)\n", failures);
    return failures ? 1 : 0;
}
