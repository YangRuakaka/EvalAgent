#!/usr/bin/env python3
"""
Split task groups with more than 2 data files into multiple subgroups.
Each subgroup will have at most 2 data files.
"""

import shutil
import json
from pathlib import Path


def split_group_folders(base_dir: Path) -> None:
    """
    For each task folder with > 2 JSON files, split them into subfolders.
    
    Example:
      buy_milk/ (6 files) -> buy_milk_1/ (2 files), buy_milk_2/ (2 files), buy_milk_3/ (2 files)
    """
    
    # Get all task folders
    task_folders = sorted([d for d in base_dir.iterdir() if d.is_dir()])
    
    for task_folder in task_folders:
        # List all JSON files in this task folder
        json_files = sorted([f for f in task_folder.glob('*.json') if f.is_file()])
        
        if len(json_files) <= 2:
            print(f"✓ {task_folder.name}: {len(json_files)} files (no split needed)")
            continue
        
        print(f"⚠ {task_folder.name}: {len(json_files)} files (splitting into groups of 2)")
        
        # Calculate how many subgroups we need
        num_subgroups = (len(json_files) + 1) // 2  # Round up
        
        # Create 'original' backup if first time processing
        backup_folder = task_folder.parent / f"{task_folder.name}_original_backup"
        if not backup_folder.exists():
            shutil.copytree(task_folder, backup_folder)
            print(f"  → Backed up original to {backup_folder.name}/")
        
        # Create new subfolders and distribute files
        for group_idx in range(1, num_subgroups + 1):
            subfolder = task_folder.parent / f"{task_folder.name}_{group_idx}"
            
            # Remove if exists (in case we're re-running)
            if subfolder.exists():
                shutil.rmtree(subfolder)
            
            subfolder.mkdir(parents=True, exist_ok=True)
            
            # Distribute files: group i gets files from index (i-1)*2 to i*2
            start_idx = (group_idx - 1) * 2
            end_idx = min(group_idx * 2, len(json_files))
            
            for file_idx in range(start_idx, end_idx):
                src_file = json_files[file_idx]
                dst_file = subfolder / src_file.name
                shutil.copy2(src_file, dst_file)
                print(f"  → {subfolder.name}/{src_file.name}")
        
        # Remove original folder after successful split
        shutil.rmtree(task_folder)
        print(f"  → Removed original {task_folder.name}/ folder")
    
    print("\n✓ Dataset splitting complete!")


if __name__ == "__main__":
    DATA_DIR = Path("technical_evaluation/dataset/dataset_grouped_by_task")
    
    if not DATA_DIR.exists():
        print(f"Error: {DATA_DIR} not found")
        exit(1)
    
    split_group_folders(DATA_DIR)
