from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
from torchvision.models import resnet18

# Support running as `python test/...py` without package install.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from torchlit import TrainTracker, TrainTrackerConfig


def choose_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CIFAR10 + ResNet18 Torchlit run.")
    parser.add_argument("--run-root", default="runs", help="Run output root directory.")
    parser.add_argument("--data-dir", default="data", help="CIFAR10 dataset directory.")
    parser.add_argument("--epochs", type=int, default=5, help="Epochs to run.")
    parser.add_argument("--batch-size", type=int, default=128, help="Train batch size.")
    parser.add_argument(
        "--num-workers", type=int, default=2, help="DataLoader workers."
    )
    parser.add_argument("--lr", type=float, default=1e-3, help="Learning rate.")
    parser.add_argument(
        "--steps-per-epoch",
        type=int,
        default=0,
        help="If > 0, truncate each epoch to this many train steps.",
    )
    parser.add_argument(
        "--val-interval",
        type=int,
        default=1,
        help="Run validation every N epochs (0 disables validation).",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=20,
        help="Print progress every N train steps.",
    )
    parser.add_argument(
        "--sleep-per-step",
        type=float,
        default=0.0,
        help="Optional sleep seconds per step for slower visual inspection.",
    )
    parser.add_argument(
        "--web-port",
        type=int,
        default=8514,
        help="Streamlit port for auto-launched viewer.",
    )
    parser.add_argument(
        "--strict-cifar10",
        action="store_true",
        help="Fail if CIFAR10 is unavailable (do not fallback to FakeData).",
    )
    return parser.parse_args()


def load_datasets(
    args: argparse.Namespace,
) -> tuple[torch.utils.data.Dataset, torch.utils.data.Dataset, str]:
    train_tf = transforms.Compose(
        [
            transforms.RandomCrop(32, padding=4),
            transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2470, 0.2435, 0.2616)),
        ]
    )
    val_tf = transforms.Compose(
        [
            transforms.ToTensor(),
            transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2470, 0.2435, 0.2616)),
        ]
    )

    data_root = str(Path(args.data_dir).resolve())
    try:
        train_ds = datasets.CIFAR10(
            root=data_root, train=True, download=True, transform=train_tf
        )
        val_ds = datasets.CIFAR10(
            root=data_root, train=False, download=True, transform=val_tf
        )
        return train_ds, val_ds, "CIFAR10"
    except Exception as e:
        if args.strict_cifar10:
            raise
        print(f"[warn] CIFAR10 unavailable ({e}); using FakeData fallback.")
        fake_train = datasets.FakeData(
            size=max(20000, args.batch_size * max(1, args.epochs) * 100),
            image_size=(3, 32, 32),
            num_classes=10,
            transform=val_tf,
        )
        fake_val = datasets.FakeData(
            size=2000,
            image_size=(3, 32, 32),
            num_classes=10,
            transform=val_tf,
        )
        return fake_train, fake_val, "FakeData(offline-fallback)"


def evaluate(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    epoch: int,
    tracker: TrainTracker,
    global_step: int,
) -> tuple[float, float]:
    model.eval()
    total_loss = 0.0
    total_correct = 0
    total_seen = 0
    with torch.no_grad():
        for x, y in loader:
            x = x.to(device)
            y = y.to(device)
            logits = model(x)
            loss = criterion(logits, y)
            total_loss += float(loss.item()) * y.size(0)
            total_correct += int((logits.argmax(dim=1) == y).sum().item())
            total_seen += int(y.size(0))

    val_loss = total_loss / max(1, total_seen)
    val_acc = total_correct / max(1, total_seen)
    tracker.step_end(
        step=global_step,
        epoch=epoch,
        split="val",
        metrics={"loss": val_loss, "acc": val_acc},
    )
    return val_loss, val_acc


def main() -> int:
    args = parse_args()
    torch.manual_seed(42)

    device = choose_device()
    print(f"[info] device={device}")

    train_ds, val_ds, dataset_name = load_datasets(args)
    train_loader = DataLoader(
        train_ds,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=(device.type == "cuda"),
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=(device.type == "cuda"),
    )

    model = resnet18(weights=None, num_classes=10).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    criterion = nn.CrossEntropyLoss()

    cfg = TrainTrackerConfig(
        auto_launch_web=True,
        web_open_browser=True,
        web_port=int(args.web_port),
        web_once_per_process=True,
        web_wait_ready=True,
    )

    global_step = 0
    with TrainTracker(
        model,
        opt,
        run_root=args.run_root,
        name="cifar10-resnet18",
        config=cfg,
        extra_meta={
            "dataset": dataset_name,
            "epochs": int(args.epochs),
            "batch_size": int(args.batch_size),
            "steps_per_epoch": int(args.steps_per_epoch),
        },
    ) as tracker:
        print(f"[info] streamlit_url={tracker.web_url} ready={tracker.web_ready}")
        for epoch in range(args.epochs):
            model.train()
            for step_in_epoch, (x, y) in enumerate(train_loader):
                if args.steps_per_epoch > 0 and step_in_epoch >= args.steps_per_epoch:
                    break

                x = x.to(device)
                y = y.to(device)

                opt.zero_grad(set_to_none=True)
                logits = model(x)
                loss = criterion(logits, y)
                loss.backward()
                opt.step()

                acc = float((logits.argmax(dim=1) == y).float().mean().item())
                loss_value = float(loss.item())
                tracker.step_end(
                    step=global_step,
                    epoch=epoch,
                    split="train",
                    metrics={"loss": loss_value, "acc": acc},
                )

                if args.log_every > 0 and (global_step % args.log_every == 0):
                    print(
                        f"[train] epoch={epoch + 1}/{args.epochs} "
                        f"step={global_step} loss={loss_value:.4f} acc={acc:.4f}"
                    )

                global_step += 1
                if args.sleep_per_step > 0:
                    time.sleep(args.sleep_per_step)

            if args.val_interval > 0 and ((epoch + 1) % args.val_interval == 0):
                val_loss, val_acc = evaluate(
                    model=model,
                    loader=val_loader,
                    criterion=criterion,
                    device=device,
                    epoch=epoch,
                    tracker=tracker,
                    global_step=global_step,
                )
                print(
                    f"[val] epoch={epoch + 1}/{args.epochs} "
                    f"step={global_step} loss={val_loss:.4f} acc={val_acc:.4f}"
                )

    print(f"[info] run_id={tracker.run_id}")
    print(f"[info] run_dir={tracker.run_dir}")
    print(f"[info] dataset={dataset_name}")
    print(f"[result] streamlit_ready={tracker.web_ready}")
    return 0 if tracker.web_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
