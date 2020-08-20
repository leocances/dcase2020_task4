#!/bin/sh

path_torch="/logiciels/containerCollections/CUDA10/pytorch.sif"
path_py="$HOME/miniconda3/envs/dcase2020/bin/python"
path_script="$HOME/root/task4/standalone/main_onehot_tag.py"

run="sf"
suffix="SF"

tmp_file=".tmp_sbatch.sh"
name="UT$suffix"
out_file="$HOME/logs/UBS8K_%j_${run}_${suffix}.out"
err_file="$HOME/logs/UBS8K_%j_${run}_${suffix}.err"

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

srun singularity exec $path_torch $path_py $path_script \
	--run "$run" \
	--suffix "$suffix" \
	--nb_epochs 100 \
	--experimental "None" \
	--optimizer "Adam" \
	--scheduler "None" \
	--use_rampup false \
	--nb_rampup_steps 10 \
	--cross_validation false \
	--threshold_confidence 0.9 \
	--lr 1e-3 \
	--nb_augms 2 \
	--nb_augms_strong 2 \
	--lambda_u 1.0 \
	--lambda_u1 0.5 \
	--lambda_r 0.5 \
	--batch_size_s 64 \
	--batch_size_u 64 \
	--label_smoothing 0.000 \
	--rampup_each_epoch true \
	--shuffle_s_with_u true \
	--criterion_name_u "cross_entropy" \
	--use_wlu false \
	--wlu_on_epoch true \
	--wlu_steps 10 \
	--dropout 0.5 \
	--supervised_augment "none" \
	--standardize false \
	--self_supervised_component "flips" \
	--dataset_path "/projets/samova/leocances/UrbanSound8K/" \
	--logdir "$HOME/root/tensorboard/UBS8K/fold_10_CNN03/" \
	--checkpoint_path "$HOME/root/task4/models/" \
	--dataset_name "UBS8K" \
	--nb_classes 10 \
	--supervised_ratio 0.10 \
	--model "CNN03Rot" \
	--num_workers_s 4 \
	--num_workers_u 4 \
	--checkpoint_metric_name "acc" \
	--write_results true \
	--debug_mode false \

EOT

sbatch $tmp_file
