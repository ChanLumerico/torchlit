import torch
from torch.utils.data import DataLoader
from transformers import AutoImageProcessor, ResNetForImageClassification
from datasets import load_dataset
import evaluate

import torchlit


def run_real_test():
    print("Loading CIFAR-10 Dataset from Hugging Face...")
    dataset = load_dataset(
        "cifar10", split="train[:5%]"
    )  # Use a tiny subset for quick demo

    print("Loading Pretrained ResNet-50 from Microsoft...")
    model_name = "microsoft/resnet-50"
    processor = AutoImageProcessor.from_pretrained(model_name)

    # CIFAR-10 has 10 classes
    model = ResNetForImageClassification.from_pretrained(
        model_name, num_labels=10, ignore_mismatched_sizes=True
    )

    # Setup Device
    device = torch.device(
        "cuda"
        if torch.cuda.is_available()
        else "mps" if torch.backends.mps.is_available() else "cpu"
    )
    model.to(device)

    # Preprocess
    def transform(example_batch):
        inputs = processor([x for x in example_batch["img"]], return_tensors="pt")
        inputs["labels"] = example_batch["label"]
        return inputs

    dataset.set_transform(transform)
    dataloader = DataLoader(dataset, batch_size=32, shuffle=True)

    optimizer = torch.optim.AdamW(model.parameters(), lr=5e-5)

    print(f"Starting real training loop on {device}...")

    # Use torchlit to monitor the real model
    with torchlit.Monitor(exp_name="cifar10_resnet50", model=model) as logger:

        model.train()
        global_step = 0

        for epoch in range(1, 4):  # Train for 3 quick epochs
            print(f"--- Epoch {epoch} ---")
            for batch in dataloader:
                global_step += 1

                # Move to device
                pixel_values = batch["pixel_values"].to(device)
                labels = batch["labels"].to(device)

                # Forward Pass
                outputs = model(pixel_values=pixel_values, labels=labels)
                loss = outputs.loss

                # Backward Pass
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

                # Calculate Accuracy (on batch for simplicity)
                preds = outputs.logits.argmax(-1)
                acc = (preds == labels).float().mean().item()

                # Log to Torchlit dynamically!
                logger.log(
                    {
                        "loss": loss.item(),
                        "accuracy": acc,
                        "learning_rate": optimizer.param_groups[0]["lr"],
                        "epoch": epoch,
                    },
                    step=global_step,
                )

                if global_step % 5 == 0:
                    print(
                        f"Step {global_step} | Loss: {loss.item():.4f} | Acc: {acc:.4f}"
                    )


if __name__ == "__main__":
    run_real_test()
