#!/bin/sh

run=$1
suffix=$2
experimental=$3

path_torch="/logiciels/containerCollections/CUDA10/pytorch.sif"

path_py="$HOME/miniconda3/envs/dcase2020/bin/python"
path_script="$HOME/root/task4/standalone/match_multihot_loc.py"
path_dataset="/projets/samova/leocances/dcase2020/DESED/"
path_board="$HOME/root/tensorboard_DESED_LOC/"
path_checkpoint="$HOME/root/task4/models/"

tmp_file=".tmp_sbatch.sh"
name="DLOC_$run"
out_file="$HOME/logs/DESED_LOC_%j_$run.out"
err_file="$HOME/logs/DESED_LOC_%j_$run.err"

cat << EOT > $tmp_file
#!/bin/sh

#SBATCH --job-name=$name
#SBATCH --output=$out_file
#SBATCH --error=$err_file
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=5
# For GPU nodes
#SBATCH --partition="GPUNodes"
#SBATCH --gres=gpu:1
#SBATCH --gres-flags=enforce-binding

module purge
module load singularity/3.0.3

srun singularity exec $path_torch $path_py $path_script --dataset $path_dataset --logdir $path_board --path_checkpoint $path_checkpoint --debug False --from_disk False --batch_size_s 64 --batch_size_u 64 --num_workers_s 4 --num_workers_u 4 --nb_epochs 100 --write_results True --use_rampup True --use_alignment False --threshold_multihot 0.5 --threshold_confidence 0.999 --run "$run" --experimental "$experimental" --suffix "$suffix"

EOT

sbatch $tmp_file