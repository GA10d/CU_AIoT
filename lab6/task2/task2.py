import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

from google import genai


TASK1_DIR = Path(__file__).resolve().parents[1] / "task1"
sys.path.insert(0, str(TASK1_DIR))

from dataset import UCIHARSignals


API_KEY = ""
MODEL = "gemini-3.5-flash-lite"

CHANNELS = (
    "total_acc_x",
    "total_acc_y",
    "total_acc_z",
    "body_gyro_x",
    "body_gyro_y",
    "body_gyro_z",
)

LABELS = (
    "WALKING",
    "WALKING_UPSTAIRS",
    "WALKING_DOWNSTAIRS",
    "SITTING",
    "STANDING",
    "LAYING",
)


def make_prompt(sample, style):
    # 保留全部 128 个点，仅将数值四舍五入以缩短提示词。
    sensor_data = {
        name: [round(float(value), 4) for value in sample[i]]
        for i, name in enumerate(CHANNELS)
    }

    common = (
        "Identify the human activity from this sensor window.\n"
        "Device: Smartphone\n"
        "Attached location: Waist\n"
        "Setting: Controlled activity recording, UCI HAR dataset\n"
        "Sampling rate: 50 Hz\n"
        "Window length: 128 samples, approximately 2.56 seconds\n"
        "Accelerometer: total acceleration including gravity, in g\n"
        "Gyroscope: angular velocity, in radians per second\n"
        f"Candidate activities: {', '.join(LABELS)}\n"
        "Each array below contains one channel in time order.\n"
        f"Sensor data: {json.dumps(sensor_data)}\n\n"
    )

    if style == "cot":
        return common + (
            "Explain your reasoning step by step, then give the activity. "
            "Choose exactly one candidate activity. "
            "End with a line in this exact format:\n"
            "FINAL_LABEL: <ACTIVITY>"
        )

    return common + (
        "Give only the activity label. "
        "Return exactly one candidate activity name, without explanation."
    )


def extract_label(text, style):
    text = text.strip().upper()

    if style == "direct":
        # 允许简单的 Markdown 包装，但不接受额外解释。
        label = text.strip("`* \n\r\t.")
        return label if label in LABELS else None

    options = "|".join(sorted(LABELS, key=len, reverse=True))
    matches = re.findall(
        rf"FINAL_LABEL:\s*({options})\b",
        text,
    )
    return matches[-1] if matches else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--pause", type=float, default=5)
    args = parser.parse_args()

    data_dir = TASK1_DIR.parent / "data" / "UCI HAR Dataset"
    dataset = UCIHARSignals(data_dir, split="test")

    if not 1 <= args.n <= len(dataset):
        raise ValueError("--n must be between 1 and the dataset size")

    # 固定种子，方便复现实验；不重复抽样。
    indices = random.Random(args.seed).sample(
        range(len(dataset)), args.n
    )

    client = genai.Client(api_key=API_KEY)

    # 每次运行使用独立目录，避免覆盖之前的结果。
    output_dir = (
        Path(__file__).resolve().parent
        / "results"
        / str(time.time_ns())
    )
    output_dir.mkdir(parents=True)

    metadata = {
        "model": MODEL,
        "seed": args.seed,
        "indices": indices,
        "temperature": 0,
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    results = []

    for number, index in enumerate(indices, start=1):
        sample, _, true_label = dataset[index]

        print(f"\n{'=' * 50}")
        print(f"Sample {number}/{args.n}, dataset index: {index}")
        print("True label:", true_label)

        row = {
            "sample_index": index,
            "true_label": true_label,
        }

        for style in ("cot", "direct"):
            prompt = make_prompt(sample, style)

            # 保存实际发送的提示词，不包含 API key。
            (output_dir / f"{index}_{style}_prompt.txt").write_text(
                prompt, encoding="utf-8"
            )

            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={"temperature": 0},
            )

            raw_output = response.text or ""
            prediction = extract_label(raw_output, style)
            correct = prediction == true_label

            row[style] = {
                "raw_output": raw_output,
                "prediction": prediction,
                "correct": correct,
            }

            # 每次调用后保存，出错时仍保留已完成的结果。
            record = {
                "sample_index": index,
                "true_label": true_label,
                "style": style,
                **row[style],
            }
            with (output_dir / "responses.jsonl").open(
                "a", encoding="utf-8"
            ) as file:
                file.write(json.dumps(record) + "\n")

            print(f"\n[{style.upper()}]")
            print(raw_output)
            print("Parsed label:", prediction)
            print("Correct:", correct)

            time.sleep(args.pause)

        results.append(row)

    summary = {}

    for style in ("cot", "direct"):
        correct_count = sum(row[style]["correct"] for row in results)
        invalid_count = sum(
            row[style]["prediction"] is None for row in results
        )

        summary[style] = {
            "correct": correct_count,
            "total": args.n,
            "accuracy": correct_count / args.n,
            "invalid_outputs": invalid_count,
        }

    agreement_count = sum(
        row["cot"]["prediction"] is not None
        and row["cot"]["prediction"] == row["direct"]["prediction"]
        for row in results
    )

    summary["agreement_rate"] = agreement_count / args.n

    (output_dir / "results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    print(f"\n{'=' * 50}")
    for style in ("cot", "direct"):
        item = summary[style]
        print(
            f"{style.upper()} accuracy: "
            f"{item['correct']}/{item['total']} "
            f"= {item['accuracy']:.1%}"
        )
        print("Invalid outputs:", item["invalid_outputs"])

    print(f"Agreement rate: {summary['agreement_rate']:.1%}")
    print("Results saved to:", output_dir)


if __name__ == "__main__":
    main()