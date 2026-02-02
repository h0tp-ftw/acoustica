import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src"))

from acoustic_engine.tester.display import Display
from acoustic_engine.tester.runner import TestRunner


def run_test(profile, audio, chunk, dropout):
    print(f"\n--- Testing {profile} with chunk={chunk}, dropout={dropout} ---")
    display = Display(verbose=False)
    # Don't use high_resolution=True here to avoid overwrites
    runner = TestRunner(
        profile_path=Path(profile),
        chunk_size=chunk,
        verbose=False,
        display=display
    )
    # Manually set the tighter thresholds we want for high-res
    runner.generator.dropout_tolerance = dropout
    runner.generator.min_tone_duration = 0.02

    print(f"Generator config: chunk={runner.generator.chunk_size}, dropout={runner.generator.dropout_tolerance}")

    runner.run_file(Path(audio))
    runner.show_results()

run_test("profiles/smoke_alarm_t3.yaml", "smoke_alarm.mp3", 512, 0.05)
run_test("CO_Sensor_profile.yaml", "alarm_recording.mp3", 512, 0.05)
