# cFS application build for ARIA_ADV.
# Drop into the host project's apps/ directory under cFS;
# the standard mission-build picks it up automatically.

cmake_minimum_required(VERSION 3.18)
project(ARIA_ADV C)

# Public headers consumed by other cFS apps + the host build.
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/inc)
include_directories(${MISSION_BINARY_DIR}/inc)
include_directories(${CFE_API_INC_DIR})

# ── Application library ──────────────────────────────────────────
aria_adv_SRC
add_cfe_app(aria_adv
    src/aria_adv_app.c
    src/aria_adv_constitution.c
)

# ── Tables (loaded by cFE Table Services at boot). ──────────────
add_cfe_tables(aria_adv tables/aria_adv_constitution_tbl.c)

# ── Unit tests (cFS UT framework). ─────────────────────────────
if(ENABLE_UNIT_TESTS)
    add_subdirectory(tests)
endif()
