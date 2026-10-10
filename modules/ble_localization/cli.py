"""Optional model prediction CLI, separate from mesh service startup."""

import argparse


def main() -> None:
    from ble_localization.ble_train_model import predict_location
    from ble_localization.main import _load_from_file, _load_from_json, _load_sample

    parser = argparse.ArgumentParser(description="Predict survivor coordinates from BLE relay RSSI data.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--relay-json", help="Relay data as JSON array shaped (NUM_RELAYS, 3).")
    group.add_argument("--relay-file", help="Path to a JSON file containing relay data array.")
    group.add_argument("--sample-index", type=int, help="Use a sample row from the dataset by index.")
    args = parser.parse_args()
    if args.relay_json:
        relay_data = _load_from_json(args.relay_json)
    elif args.relay_file:
        relay_data = _load_from_file(args.relay_file)
    else:
        relay_data = _load_sample(args.sample_index)
    pred_x, pred_y = predict_location(relay_data)
    print(f"Predicted survivor location: x={pred_x:.2f}, y={pred_y:.2f}")
