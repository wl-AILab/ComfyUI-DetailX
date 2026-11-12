import argparse
import json
import sys
from pathlib import Path

from .client import DetailXClient
from .errors import DetailXError
from .models import GenerationOptions, PreparedGeneration


def main():
    parser = argparse.ArgumentParser(prog="detailx")
    parser.add_argument("--state-dir", default=None)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("account")
    commands.add_parser("capabilities")
    upload = commands.add_parser("upload")
    upload.add_argument("file", type=Path)
    upload.add_argument("--request-id", required=True)
    for name in ("quote", "prepare"):
        command = commands.add_parser(name)
        source = command.add_mutually_exclusive_group(required=True)
        source.add_argument("--upload-id")
        source.add_argument("--source-result-id")
        command.add_argument("--resolution", default="4K", choices=["720p", "1080p", "2K", "4K"])
        command.add_argument("--fps", type=int, default=-1, choices=[-1, 24, 30, 60])
        command.add_argument("--detail", choices=["1", "2", "3"])
        if name == "prepare":
            command.add_argument("--request-id", required=True)
            command.add_argument("--max-precharge-credits", required=True, type=int)
            command.add_argument("--output", type=Path, required=True)
    submit = commands.add_parser("submit")
    submit.add_argument("prepared", type=Path)
    for name in ("get", "wait", "download"):
        command = commands.add_parser(name)
        command.add_argument("generation_id")
        if name == "wait":
            command.add_argument("--timeout", type=float, default=1800)
        if name == "download":
            command.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        with DetailXClient(state_dir=args.state_dir) as client:
            if args.command in ("account", "capabilities"):
                result = getattr(client, args.command)()
            elif args.command == "upload":
                result = client.upload_video(args.file, request_id=args.request_id, on_progress=lambda p: print(json.dumps(p), file=sys.stderr))
            elif args.command in ("quote", "prepare"):
                options = GenerationOptions(args.resolution, args.fps, args.detail)
                kwargs = {"upload_id": args.upload_id, "source_result_id": args.source_result_id}
                if args.command == "quote":
                    result = client.estimate(options, **kwargs)
                else:
                    result = client.prepare_generation(options, **kwargs, request_id=args.request_id, max_precharge_credits=args.max_precharge_credits).to_dict()
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
            elif args.command == "submit":
                result = client.submit(PreparedGeneration.from_dict(json.loads(args.prepared.read_text(encoding="utf-8"))))
            elif args.command == "get":
                result = client.get_generation(args.generation_id)
            elif args.command == "wait":
                result = client.wait(args.generation_id, timeout=args.timeout)
            else:
                result = {"file": str(client.download_result(args.generation_id, args.output))}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (DetailXError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
