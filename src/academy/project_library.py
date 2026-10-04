from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


PUBLICATION_STATUSES = {"draft", "published"}
VERIFICATION_STATES = {
    "not-tested",
    "reference-reviewed",
    "editorially-reviewed",
    "observed",
    "hardware-verified",
    "not-hardware-verified",
}


@dataclass(frozen=True)
class HardwareItem:
    quantity: str
    item: str
    model: str
    revision: str
    purpose: str


@dataclass(frozen=True)
class WiringConnection:
    board_pin: str
    module_pin: str
    signal: str
    electrical_note: str


@dataclass(frozen=True)
class ReferenceLink:
    label: str
    url: str
    scope: str


@dataclass(frozen=True)
class Verification:
    prompt_review: str
    build: str
    upload: str
    wiring: str
    physical_test: str


@dataclass(frozen=True)
class Video:
    name: str
    url: str
    thumbnail_url: str
    upload_date: str
    duration: str
    transcript: str


@dataclass(frozen=True)
class ProjectLibraryEntry:
    project_id: str
    slug: str
    title: str
    outcome: str
    summary: str
    publication_status: str
    published_on: str
    updated_on: str
    author: str
    language: str
    board: str
    board_revision: str
    toolchain: str
    logic_level: str
    power_requirement: str
    hardware: tuple[HardwareItem, ...]
    wiring: tuple[WiringConnection, ...]
    wiring_diagram_alt: str
    wiring_note: str
    prompt_version: str
    finished_prompt: str
    usage_steps: tuple[str, ...]
    observed_results: tuple[str, ...]
    limitations: tuple[str, ...]
    related_lesson_ids: tuple[str, ...]
    references: tuple[ReferenceLink, ...]
    verification: Verification
    video: Video | None = None


FINISHED_HARDWARE_PROMPT = """You are a careful microcontroller integration assistant. Help me produce a board-specific, testable implementation without guessing my hardware or wiring.

Before you provide final wiring, firmware, build commands, upload commands or pin-dependent advice, ask me for all of the following:
1. Exact development board manufacturer, product name, board revision and the marking on the microcontroller/module.
2. Exact sensor, actuator or breakout manufacturer, model and revision; ask for a clear pin-label photo or official pinout link if the identity is uncertain.
3. Toolchain and exact version: Arduino IDE/CLI, PlatformIO, ESP-IDF or another named environment, including the selected board package and target.
4. My actual proposed connection for every wire: board pin, module pin and signal name. Do not replace this with a typical pinout.
5. Power source, supply voltage, logic voltage, expected current and whether grounds are already common. Ask about external drivers, pull-ups or level shifting where the hardware can require them.
6. Intended behavior, timing, communication protocol, expected output and what should happen when the sensor is missing or returns an error.
7. Existing source files, libraries and upload/debug port, if any.

Then normalize my answers into two short tables:
- Pin and power map: board pin | module pin | signal | voltage/current note.
- Build map: board target | framework/toolchain version | libraries | upload/debug method.

Check the proposed map against the exact board and module documentation. Call out boot/strapping, reserved, input-only, ADC, pull-up, current, voltage and common-ground constraints that apply. Never infer that a similarly named clone has the same pinout. Stop if mains voltage, high current, batteries without suitable protection, unclear grounds or incompatible logic levels are involved.

Ask: “Is this exact pin, power and build map correct? Reply YES, or reply NO with corrections.” Accept short YES/NO quick replies. Do not continue until I confirm YES.

After confirmation, provide only what is supported by the confirmed map:
1. Final BOM with exact models/revisions and required support parts.
2. Final wiring table plus a concise text diagram.
3. Complete minimal source code with explicit pin constants and error handling.
4. Reproducible build and upload steps for the confirmed toolchain.
5. Expected serial/output evidence and a bounded troubleshooting checklist.
6. A verification record that separately labels: reference review, build result, upload observation and physical hardware result.

Never report a build, upload or physical test as successful unless I provide the corresponding real result or you actually performed that exact check with an authorized connected tool. Preserve uncertainty and cite the exact documentation used."""


PROJECTS = (
    ProjectLibraryEntry(
        project_id="TTC-MCU-001",
        slug="esp32-bme280-planning-starter",
        title="ESP32 + BME280 planning starter",
        outcome="Turn an exact ESP32 board and BME280 breakout into a confirmed pin-and-power plan before generating firmware.",
        summary=(
            "A reference-reviewed teaching example for an I2C environmental sensor. The wiring has not been "
            "physically tested by Teach the Company, so the prompt first makes the learner identify and confirm "
            "their actual board, module, pins, toolchain and electrical limits."
        ),
        publication_status="published",
        published_on="2026-10-04",
        updated_on="2026-10-04",
        author="Finn Andre Hotvedt",
        language="en",
        board="Espressif ESP32-DevKitC V4 example family",
        board_revision="The actual board revision and module marking must be confirmed by the learner.",
        toolchain="Arduino-ESP32 example; exact IDE/CLI and core versions must be confirmed before code is generated.",
        logic_level="3.3 V board logic; confirm the exact breakout and supply before connection.",
        power_requirement="USB-powered development board; sensor current and complete power budget must be checked for the exact parts.",
        hardware=(
            HardwareItem(
                "1",
                "Development board",
                "Espressif ESP32-DevKitC V4 example family",
                "Confirm the printed board and ESP32 module revision",
                "Runs the firmware and provides the example I2C bus.",
            ),
            HardwareItem(
                "1",
                "Environmental sensor breakout",
                "Adafruit BME280 I2C or SPI breakout",
                "Confirm the exact product/revision and pin labels",
                "Measures temperature, humidity and pressure in the teaching example.",
            ),
            HardwareItem("4", "Jumper wire", "Female-to-female", "Inspect before use", "Carries 3.3 V, ground, SDA and SCL."),
            HardwareItem("1", "USB data cable", "Suitable for the exact development board", "Known data-capable cable", "Powers and uploads to the board."),
        ),
        wiring=(
            WiringConnection("3V3", "VIN", "Power", "Example uses 3.3 V so power and logic share the same level; confirm the exact breakout."),
            WiringConnection("GND", "GND", "Common ground", "Connect ground before interpreting signal behavior."),
            WiringConnection("GPIO21", "SDI", "I2C SDA", "Arduino-ESP32 documentation lists GPIO21 as the generic ESP32 default SDA pin."),
            WiringConnection("GPIO22", "SCK", "I2C SCL", "Arduino-ESP32 documentation lists GPIO22 as the generic ESP32 default SCL pin."),
        ),
        wiring_diagram_alt=(
            "Reference diagram: ESP32 3V3 to BME280 VIN, GND to GND, GPIO21 to SDI/SDA and GPIO22 to SCK/SCL. "
            "Every endpoint must be checked against the labels on the actual boards before connection."
        ),
        wiring_note=(
            "Reference-reviewed against the linked Espressif Arduino I2C and Adafruit BME280 pinout documentation. "
            "Not physically tested by Teach the Company. Some clones, revisions and other BME280 breakouts differ."
        ),
        prompt_version="1.0.0",
        finished_prompt=FINISHED_HARDWARE_PROMPT,
        usage_steps=(
            "Copy or download the finished prompt.",
            "Paste it into the agent you use for the project.",
            "Answer with the exact markings, toolchain, real wiring proposal, power information and intended behavior.",
            "Check the normalized pin/power and build maps; reply YES only when every row matches the physical hardware.",
            "Generate and build the minimal firmware, then record build, upload and physical results separately.",
        ),
        observed_results=(
            "The public prompt and project record passed automated content, route and consistency tests in the Teach the Company source tree.",
            "No firmware build was run for this adaptable example.",
            "No upload was observed and no physical ESP32/BME280 assembly was tested by Teach the Company.",
        ),
        limitations=(
            "This is a planning and teaching foundation, not a claim that one exact hardware assembly was completed.",
            "Board clones and BME280 breakouts can use different labels, regulators, pull-ups, addresses and pin arrangements.",
            "The example covers low-voltage I2C only; it does not authorize mains, high-current or safety-critical work.",
            "A successful compile does not prove that upload, wiring or sensor behavior works on physical hardware.",
        ),
        related_lesson_ids=("TTC-101", "TTC-104", "TTC-114", "TTC-115", "TTC-117"),
        references=(
            ReferenceLink(
                "Teach the Company source on GitHub",
                "https://github.com/finnandrehotvedt/teach-the-company",
                "Open-source application and Docker framework that publishes this project library; not firmware or physical-test evidence.",
            ),
            ReferenceLink(
                "Teach the Company source on GitLab",
                "https://gitlab.finnandre.no/finnandrehotvedt/teach-the-company",
                "Open-source application and Docker framework mirror with version history; not firmware or physical-test evidence.",
            ),
            ReferenceLink(
                "Espressif Arduino-ESP32 I2C API",
                "https://docs.espressif.com/projects/arduino-esp32/en/latest/api/i2c.html",
                "Official generic ESP32 Arduino I2C defaults and API behavior.",
            ),
            ReferenceLink(
                "Espressif ESP32-DevKitC V4 guide",
                "https://docs.espressif.com/projects/esp-idf/en/latest/esp32/hw-reference/esp32/get-started-devkitc.html",
                "Official board overview, header and power guidance; the actual board revision still must be identified.",
            ),
            ReferenceLink(
                "Adafruit BME280 pinouts",
                "https://learn.adafruit.com/adafruit-bme280-humidity-barometric-pressure-temperature-sensor-breakout/pinouts",
                "Official pin labels, logic/power guidance and I2C address notes for the named breakout.",
            ),
        ),
        verification=Verification(
            prompt_review="editorially-reviewed",
            build="not-tested",
            upload="not-tested",
            wiring="reference-reviewed",
            physical_test="not-hardware-verified",
        ),
    ),
)


def validate_project_library(entries: tuple[ProjectLibraryEntry, ...]) -> None:
    slugs: set[str] = set()
    project_ids: set[str] = set()
    for entry in entries:
        if entry.publication_status not in PUBLICATION_STATUSES:
            raise ValueError(f"Invalid publication status for {entry.slug}.")
        if not entry.slug or entry.slug in slugs or entry.project_id in project_ids:
            raise ValueError("Project library slugs and IDs must be non-empty and unique.")
        slugs.add(entry.slug)
        project_ids.add(entry.project_id)
        states = (
            entry.verification.prompt_review,
            entry.verification.build,
            entry.verification.upload,
            entry.verification.wiring,
            entry.verification.physical_test,
        )
        if any(state not in VERIFICATION_STATES for state in states):
            raise ValueError(f"Invalid verification state for {entry.slug}.")
        if entry.publication_status == "published" and not all(
            (entry.title, entry.outcome, entry.summary, entry.board, entry.hardware, entry.wiring, entry.finished_prompt, entry.references)
        ):
            raise ValueError(f"Published project {entry.slug} is incomplete.")
        for reference in entry.references:
            parsed = urlparse(reference.url)
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValueError(f"Public reference for {entry.slug} must use an absolute HTTPS URL.")
        if entry.video:
            video_values = (
                entry.video.name,
                entry.video.url,
                entry.video.thumbnail_url,
                entry.video.upload_date,
                entry.video.duration,
                entry.video.transcript,
            )
            if not all(video_values):
                raise ValueError(f"Video metadata for {entry.slug} must be complete or absent.")
        if entry.verification.physical_test == "hardware-verified" and not any(
            "physical" in result.lower() and "not" not in result.lower() for result in entry.observed_results
        ):
            raise ValueError(f"Hardware-verified project {entry.slug} lacks a physical result.")


def published_projects(entries: tuple[ProjectLibraryEntry, ...] = PROJECTS) -> tuple[ProjectLibraryEntry, ...]:
    return tuple(entry for entry in entries if entry.publication_status == "published")


validate_project_library(PROJECTS)

PUBLISHED_PROJECTS = published_projects()
PUBLISHED_PROJECT_BY_SLUG = {entry.slug: entry for entry in PUBLISHED_PROJECTS}
