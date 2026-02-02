#!/bin/bash
set -e

# Function to check if a directory is empty and populate it from defaults
check_and_populate() {
    local target_dir="$1"
    local source_dir="$2"

    # Ensure target directory exists
    if [ ! -d "$target_dir" ]; then
        echo "Creating directory: $target_dir"
        mkdir -p "$target_dir"
    fi

    # Check if target directory is empty
    if [ -z "$(ls -A "$target_dir")" ]; then
        echo "Volume mounted at $target_dir is empty. Populating from defaults..."
        if [ -d "$source_dir" ]; then
            cp -r "$source_dir"/. "$target_dir"/
            echo "Successfully populated $target_dir"
        else
            echo "Warning: Default source $source_dir not found. Skipping."
        fi
    else
        echo "Directory $target_dir contains files. Skipping population."
    fi
}

# Check and populate the specific asset directories
check_and_populate "/app/overlays" "/defaults/overlays"
check_and_populate "/app/textures" "/defaults/textures"
check_and_populate "/app/fonts" "/defaults/fonts"

# Execute the main container command
exec "$@"
