import torch
import torch.nn as nn
import pickle
from tqdm import tqdm
from sklearn.metrics import accuracy_score, recall_score, f1_score
from multiprocessing import cpu_count
import numpy as np
from torch.utils.data import DataLoader, ConcatDataset
from create_dataset import PreprocessedDataset, collate_fn
from model.model import PedestrianCrossingPredictor

def validation(model, criterion, val_loader, ablation=None):
    model.eval()
    val_running_loss = 0.0
    val_preds = []
    val_targets = []

    with torch.no_grad():
        for frames, keypoints, labels, traffic_info, vehicle_info, appearance_info, attributes_info in tqdm(val_loader, desc="Validating", unit="batch"):
            frames, keypoints, traffic_info, vehicle_info, appearance_info, attributes_info, labels = (
                frames.to(device), keypoints.to(device), traffic_info.to(device), 
                vehicle_info.to(device), appearance_info.to(device), attributes_info.to(device), labels.to(device)
            )

            if ablation == 'traffic':
                traffic_info = torch.zeros_like(traffic_info)
            elif ablation == 'vehicle':
                vehicle_info = torch.zeros_like(vehicle_info)
            elif ablation == 'appearance':
                appearance_info = torch.zeros_like(appearance_info)
            elif ablation == 'attributes':
                attributes_info = torch.zeros_like(attributes_info)

            outputs = model(frames, keypoints, traffic_info, vehicle_info, appearance_info, attributes_info)
            labels = labels.unsqueeze(1).float()
            loss = criterion(outputs, labels)
            val_running_loss += loss.item()

            preds = torch.sigmoid(outputs).cpu().numpy()
            val_preds.extend(preds)
            val_targets.extend(labels.cpu().numpy())

            torch.cuda.empty_cache()

    avg_val_loss = val_running_loss / len(val_loader)
    val_accuracy = accuracy_score(val_targets, (np.array(val_preds) > 0.5).astype(int))
    val_recall = recall_score(val_targets, (np.array(val_preds) > 0.5).astype(int))
    val_f1 = f1_score(val_targets, (np.array(val_preds) > 0.5).astype(int))

    return avg_val_loss, val_accuracy, val_recall, val_f1

def evaluate_ablation(model, criterion, val_loader):
    ablations = [None, 'traffic', 'vehicle', 'appearance', 'attributes']
    results = []

    for ablation in ablations:
        print(f"Evaluating with ablation: {ablation if ablation else 'None'}")
        avg_val_loss, accuracy, recall, f1 = validation(model, criterion, val_loader, ablation)
        
        result = {
            'ablation': ablation if ablation else 'None',
            'loss': avg_val_loss,
            'accuracy': accuracy,
            'recall': recall,
            'f1_score': f1
        }
        results.append(result)
        
        print(f"Ablation: {result['ablation']}, Loss: {result['loss']:.4f}, Accuracy: {result['accuracy']:.4f}, Recall: {result['recall']:.4f}, F1 Score: {result['f1_score']:.4f}")
    
    return results

# Set the device to GPU if available, otherwise use CPU
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Initialize the model and load the trained weights
model = PedestrianCrossingPredictor().to(device)
model.load_state_dict(torch.load('./model/trained_model.pth'))
criterion = nn.BCEWithLogitsLoss()

# Load the DataLoader from a pickle file
with open('./val_loader.pkl', 'rb') as f:
    val_loader_pkl = pickle.load(f)

# Directory for validation data
val_dir = './validation_data'
# Load the preprocessed validation dataset from .pt files
val_pt = PreprocessedDataset(val_dir, transform=None)

# Create DataLoader for the .pt files
n_w = min(16, cpu_count())
validation_loader_pt = DataLoader(val_pt, batch_size = 32, shuffle = True, num_workers = n_w, pin_memory = True, collate_fn = collate_fn)

# Concatenate the DataLoaders
combined_val_dataset = ConcatDataset([val_pt, val_loader_pkl.dataset])
combined_val_loader = DataLoader(combined_val_dataset, batch_size=32, shuffle=True, num_workers=num_workers, pin_memory=True, collate_fn=collate_fn)

# Criterion for the loss function


# Evaluate the model performance with and without ablation
results = evaluate_ablation(model, criterion, combined_val_loader)

# Print the results
for result in results:
    print(f"Ablation: {result['ablation']}")
    print(f"Loss: {result['loss']:.4f}")
    print(f"Accuracy: {result['accuracy']:.4f}")
    print(f"Recall: {result['recall']:.4f}")
    print(f"F1 Score: {result['f1_score']:.4f}")
    print()