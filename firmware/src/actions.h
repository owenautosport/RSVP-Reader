// Raw input events — port of rsvp/nav/actions.py.
// The 3 physical buttons and directional touch swipes; their meaning is decided
// by the current screen (see the input controller), not here.
#pragma once

enum class Button { Left, Middle, Right };   // Slower · Play/Pause · Faster
enum class Swipe { Up, Down, Left, Right };
