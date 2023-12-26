#!/bin/bash

# Fixed starting and ending block numbers:
start_block=1
end_block=21

# Validate the fixed values:
if [[ $start_block -lt 0 || $start_block -gt 21 || $end_block -lt $start_block || $end_block -gt 21 ]]; then
  echo "Error: Fixed block numbers are outside the valid range 0-21."
  exit 1
fi

# Loop through the block numbers and execute the script:
for i in $(seq $start_block $end_block); do
  block_param="${i}"
  python main.py --tweet_block "$block_param" --methodology finevent --data_path block"$block_param"_Shape
  python main.py --tweet_block "$block_param" --methodology spacy --data_path block"$block_param"_Shape
  python main.py --tweet_block "$block_param" --methodology unsupervised --data_path block"$block_param"_Shape

  echo "Executed python main.py for $block_param finevent, spacy, unsupervised"
done

echo "All runs completed successfully."

