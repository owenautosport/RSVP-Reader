// RSVP Pocket Reader — custom case (parametric)
// =============================================================================
// A two-part clamshell around the Waveshare ESP32-S3-Touch-AMOLED-2.41 board,
// a ~1000 mAh LiPo, and 3 top-edge tactile buttons.
//
// Open in OpenSCAD. Render front_shell() and back_shell() separately and export
// each as STL to print. Everything is parametric: the board outline below is an
// ESTIMATE — measure the real board (or use the datasheet) and update the four
// board_* / screen_* numbers, then re-render. Nothing else should need changing.
//
//   View:  set SHOW = "preview" | "front" | "back"
// =============================================================================

SHOW = "preview";
$fn = 64;

// ---- Board: Waveshare ESP32-S3-Touch-AMOLED-2.41  (★ CONFIRM these 6) --------
board_w      = 52;    // landscape width  (est.)
board_h      = 41;    // height           (est.)
board_t      = 5.0;   // PCB + tallest back-side components (est.)
screen_w     = 49;    // AMOLED active-area width  (2.41" 4:3 -> ~49)
screen_h     = 37;    // AMOLED active-area height (~37)
screen_off_x = (board_w - screen_w) / 2;  // active area centered (est.)
screen_off_y = (board_h - screen_h) / 2;
glass_t      = 1.2;   // cover glass sitting above the PCB front face

// ---- Connectors on the board rim (★ confirm edge + offset) -------------------
usbc_w = 9.5; usbc_h = 3.6; usbc_cx = board_w * 0.5;   // USB-C on the BOTTOM edge
sd_w   = 12;  sd_h   = 2.0; sd_cx   = board_w * 0.78;  // microSD on the RIGHT edge

// ---- Battery: ~1000 mAh LiPo (sits behind the board) -------------------------
bat_w = 40; bat_h = 30; bat_t = 6;

// ---- Buttons: 3 tactile on the TOP edge -------------------------------------
btn_cap_d   = 4.0;                                  // through-hole for the cap
btn_xs      = [board_w*0.28, board_w*0.5, board_w*0.72];
btn_inset_z = 0;                                    // measured from the front face

// ---- Case shell --------------------------------------------------------------
wall   = 1.6;    // wall thickness
clear  = 0.6;    // clearance around the board
corner = 3.5;    // outer corner radius
lip    = 1.4;    // overlap lip between the two halves

// ---- Derived -----------------------------------------------------------------
cav_w = board_w + 2*clear;
cav_h = board_h + 2*clear;
// internal depth: glass + board + battery + a little breathing room
cav_d = glass_t + board_t + bat_t + 1.5;
out_w = cav_w + 2*wall;
out_h = cav_h + 2*wall;
out_d = cav_d + 2*wall;
seam_z = wall + glass_t + board_t + 0.8;   // split just behind the board

module rbox(w, h, d, r) {
    hull() for (x=[r, w-r], y=[r, h-r])
        translate([x, y, 0]) cylinder(r=r, h=d);
}

// Solid outer body, hollow cavity, board "keep-out" + all port/screen cutouts.
module body() {
    difference() {
        rbox(out_w, out_h, out_d, corner);
        // inner cavity (leaves a solid front bezel + back wall)
        translate([wall, wall, wall])
            rbox(cav_w, cav_h, cav_d, corner-wall);
        // screen window (front face)
        translate([wall+clear+screen_off_x, wall+clear+screen_off_y, out_d-wall-0.01])
            cube([screen_w, screen_h, wall+0.1]);
        // USB-C (bottom edge)
        translate([wall+clear+usbc_cx-usbc_w/2, -0.1, wall+glass_t+board_t/2-usbc_h/2])
            cube([usbc_w, wall+0.2, usbc_h]);
        // microSD (right edge)
        translate([out_w-wall-0.1, wall+clear+sd_cx-sd_w/2, wall+glass_t+board_t/2-sd_h/2])
            cube([wall+0.2, sd_w, sd_h]);
        // 3 button holes (top edge)
        for (bx = btn_xs)
            translate([wall+clear+bx, out_h+0.1, wall+glass_t+1.5])
                rotate([90,0,0]) cylinder(d=btn_cap_d, h=wall+0.2);
    }
}

module front_shell() {            // front: screen side + buttons (z above seam)
    intersection() { body(); translate([-1,-1,seam_z]) cube([out_w+2,out_h+2,out_d]); }
    // inner lip to mate with the back
    translate([wall-lip/2, wall-lip/2, seam_z-2])
        difference() {
            rbox(cav_w+lip, cav_h+lip, 2, corner-wall+lip/2);
            translate([lip,lip,-0.1]) rbox(cav_w-lip, cav_h-lip, 2.2, corner-wall);
        }
}

module back_shell() {             // back: board standoffs + battery pocket
    intersection() { body(); translate([-1,-1,-1]) cube([out_w+2,out_h+2,seam_z+1]); }
    // four posts to seat the board front against the glass shelf
    for (x=[wall+clear+2, wall+clear+board_w-2], y=[wall+clear+2, wall+clear+board_h-2])
        translate([x,y,wall]) cylinder(d=3, h=glass_t+0.4);
    // battery retainer walls behind the board
    translate([(out_w-bat_w)/2, (out_h-bat_h)/2, wall])
        difference() {
            rbox(bat_w+2, bat_h+2, 1, 1);
            translate([1,1,-0.1]) rbox(bat_w, bat_h, 1.2, 0.6);
        }
}

if (SHOW == "front") front_shell();
else if (SHOW == "back") back_shell();
else {                              // preview: back in place, front lifted apart
    color("SteelBlue") back_shell();
    color("Tan") translate([0,0,18]) front_shell();
}
