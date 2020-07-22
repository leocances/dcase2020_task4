#!/bin/sh

run="mm"
suffix="MMV8"

write_results=False
nb_epochs=20

path_torch="/logiciels/containerCollections/CUDA10/pytorch.sif"
path_py="$HOME/miniconda3/envs/dcase2020/bin/python"
path_script="$HOME/root/task4/standalone/match_onehot_tag.py"

path_dataset="/projets/samova/leocances/UrbanSound8K/"
path_board="$HOME/root/tensorboard/UBS8K/default/"
path_checkpoint="$HOME/root/task4/models/"

dataset_name="UBS8K"
nb_classes=10
model="CNN03Rot"
num_workers_s=4
num_workers_u=4
checkpoint_metric_name="acc"
batch_size_s=64
batch_size_u=64

scheduler="None"
use_rampup=true
cross_validation=false
threshold_confidence=0.9
nb_rampup_epochs=10
supervised_ratio=0.10
lr=1e-3
shuffle_s_with_u=true
experimental="V8"
criterion_name_u="ce"

nb_augms=2
nb_augms_strong=2
lambda_u=1.0
lambda_u1=0.5
lambda_r=0.5


$path_py $path_script \
	--run "$run" \
	--suffix "$suffix" \
	--dataset_path $path_dataset \
	--logdir $path_board \
	--checkpoint_path $path_checkpoint \
	--write_results $write_results \
	--nb_epochs $nb_epochs \
	--dataset_name $dataset_name \
	--nb_classes $nb_classes \
	--model $model \
	--num_workers_s $num_workers_s \
	--num_workers_u $num_workers_u \
	--checkpoint_metric_name $checkpoint_metric_name \
	--batch_size_s $batch_size_s \
	--batch_size_u $batch_size_u \
	--scheduler "$scheduler" \
	--use_rampup $use_rampup \
	--cross_validation $cross_validation \
	--threshold_confidence $threshold_confidence \
	--nb_rampup_epochs $nb_rampup_epochs \
	--supervised_ratio $supervised_ratio \
	--lr $lr \
	--shuffle_s_with_u $shuffle_s_with_u \
	--experimental $experimental \
	--criterion_name_u $criterion_name_u \
	--nb_augms $nb_augms \
	--nb_augms_strong $nb_augms_strong \
	--lambda_u $lambda_u \
	--lambda_u1 $lambda_u1 \
	--lambda_r $lambda_r \