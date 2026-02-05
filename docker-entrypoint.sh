#!/bin/bash
set -e

# Function to populate directory with missing files from defaults (Merge strategy)
populate_missing() {
    local target_dir="$1"
    local source_dir="$2"

    # Ensure target directory exists
    if [ ! -d "$target_dir" ]; then
        echo "Creating directory: $target_dir"
        mkdir -p "$target_dir"
    fi

    # Check if default source exists
    if [ -d "$source_dir" ]; then
        echo "Checking for new files in $source_dir to copy to $target_dir..."
        
        # cp -rn copies recursively but DOES NOT overwrite existing files.
        # This adds new system assets (e.g. new fonts) while keeping user data safe.
        cp -rn "$source_dir"/. "$target_dir"/ || true
        
        echo "Population/Update check for $target_dir completed."
    else
        echo "Warning: Default source $source_dir not found. Skipping."
    fi
}

# Check and populate/update the specific asset directories
# This will now add NEW fonts even if the folder is not empty!
populate_missing "/app/overlays" "/defaults/overlays"
populate_missing "/app/textures" "/defaults/textures"
populate_missing "/app/fonts" "/defaults/fonts"
populate_missing "/app/custom_icons" "/defaults/custom_icons"

# Execute the main container command
exec "$@"