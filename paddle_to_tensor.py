'''
@Description: 
@version: 
@Company: Thefair
@Author: Wang Yao
@Date: 2020-03-12 15:08:24
@LastEditors: Wang Yao
@LastEditTime: 2020-03-12 21:00:07
'''
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import json
import shutil
import joblib
import argparse
import numpy as np
import tensorflow as tf

import paddle.fluid as fluid
from model.ernie import ErnieConfig
from utils.init import init_checkpoint, init_pretraining_params
from finetune.classifier import create_model


parser = argparse.ArgumentParser()
parser.add_argument("--init_checkpoint", default='/media/xddz/xddz/data/ERNIE_stable-1.0.1/params', type=str, help=".")
parser.add_argument("--ernie_config_path", default='/media/xddz/xddz/data/ERNIE_stable-1.0.1/ernie_config.json', type=str, help=".")
parser.add_argument("--ernie_vocab_path", default='/media/xddz/xddz/data/ERNIE_stable-1.0.1/vocab.txt', type=str, help=".")
parser.add_argument("--max_seq_len", default=128, type=int, help=".")
parser.add_argument("--num_labels", default=2, type=int, help=".")
parser.add_argument("--use_fp16", type=bool, default=False, help="Whether to use fp16 mixed precision training.")

args = parser.parse_args()



os.environ["CUDA_VISIBLE_DEVICES"] = ""

gpus = tf.config.experimental.list_physical_devices(device_type='GPU')
for gpu in gpus:
    tf.config.experimental.set_memory_growth(gpu, True)


def check_exists(filepath):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f'{filepath} not exists.')


def convert_paddle_to_np():

    check_exists(args.init_checkpoint)
    check_exists(args.ernie_config_path)

    ernie_config = ErnieConfig(args.ernie_config_path)
    ernie_config.print_config()

    place = fluid.CPUPlace()
    exe = fluid.Executor(place)

    startup_prog = fluid.Program()
    test_program = fluid.Program()

    with fluid.program_guard(test_program, startup_prog):
        with fluid.unique_name.guard():
            _, _ = create_model(
                    args,
                    pyreader_name='test_reader',
                    ernie_config=ernie_config,
                    is_classify=True)
    
    exe.run(startup_prog)
    init_pretraining_params(
                    exe,   
                    args.init_checkpoint,
                    main_program=test_program,
                    #main_program=startup_prog,
                    use_fp16=args.use_fp16)

    name2params = {}
    prefix = args.init_checkpoint
    for var in startup_prog.list_vars():
        path = os.path.join(prefix, var.name)
        if os.path.exists(path):
            cur_tensor = fluid.global_scope().find_var(var.name).get_tensor()
            print(var.name, np.array(cur_tensor).shape)
            name2params[var.name] = np.array(cur_tensor)

    joblib.dump(name2params, 'params.dict')


def convert_np_to_tensor(params, training=False):
    tensor_prefix='bert'
    # Embeddings
    tensor_embed_prefix = f"{tensor_prefix}/embeddings"
    tf.Variable(tf.convert_to_tensor(params['pre_encoder_layer_norm_scale'], name=f"{tensor_embed_prefix}/LayerNorm/gamma"))
    tf.Variable(tf.convert_to_tensor(params['pre_encoder_layer_norm_bias'], name=f"{tensor_embed_prefix}/LayerNorm/beta"))
    tf.Variable(tf.convert_to_tensor(params['pos_embedding'], name=f"{tensor_embed_prefix}/position_embeddings"))
    tf.Variable(tf.convert_to_tensor(params['word_embedding'], name=f"{tensor_embed_prefix}/word_embeddings"))
    tf.Variable(tf.convert_to_tensor(params['sent_embedding'], name=f"{tensor_embed_prefix}/token_type_embeddings"))
    # Layers
    tensor_encoder_prefix = f"{tensor_prefix}/encoder/layer_"
    for x in range(12):
        fluid_prefix = f"encoder_layer_{x}"
        tf.Variable(tf.convert_to_tensor(
            params[f"{fluid_prefix}_post_att_layer_norm_scale"], 
            name=f"{tensor_encoder_prefix}{x}/attention/output/LayerNorm/gamma"))
        tf.Variable(tf.convert_to_tensor(
            params[f"{fluid_prefix}_post_att_layer_norm_bias"], 
            name=f"{tensor_encoder_prefix}{x}/attention/output/LayerNorm/beta"))
        tf.Variable(tf.convert_to_tensor(
            params[f"{fluid_prefix}_multi_head_att_output_fc.w_0"], 
            name=f"{tensor_encoder_prefix}{x}/attention/output/dense/kernel"))
        tf.Variable(tf.convert_to_tensor(
            params[f"{fluid_prefix}_multi_head_att_output_fc.b_0"], 
            name=f"{tensor_encoder_prefix}{x}/attention/output/dense/bias"))
        tf.Variable(tf.convert_to_tensor(
            params[f"{fluid_prefix}_multi_head_att_key_fc.w_0"], 
            name=f"{tensor_encoder_prefix}{x}/attention/self/key/kernel"))
        tf.Variable(tf.convert_to_tensor(
            params[f"{fluid_prefix}_multi_head_att_key_fc.b_0"], 
            name=f"{tensor_encoder_prefix}{x}/attention/self/key/bias"))
        tf.Variable(tf.convert_to_tensor(
            params[f"{fluid_prefix}_multi_head_att_query_fc.w_0"], 
            name=f"{tensor_encoder_prefix}{x}/attention/self/query/kernel"))
        tf.Variable(tf.convert_to_tensor(
            params[f"{fluid_prefix}_multi_head_att_query_fc.b_0"], 
            name=f"{tensor_encoder_prefix}{x}/attention/self/query/bias"))
        tf.Variable(tf.convert_to_tensor(
            params[f"{fluid_prefix}_multi_head_att_value_fc.w_0"], 
            name=f"{tensor_encoder_prefix}{x}/attention/self/value/kernel"))
        tf.Variable(tf.convert_to_tensor(
            params[f"{fluid_prefix}_multi_head_att_value_fc.b_0"], 
            name=f"{tensor_encoder_prefix}{x}/attention/self/value/bias"))
        tf.Variable(tf.convert_to_tensor(
            params[f"{fluid_prefix}_ffn_fc_0.w_0"], 
            name=f"{tensor_encoder_prefix}{x}/intermediate/dense/kernel"))
        tf.Variable(tf.convert_to_tensor(
            params[f"{fluid_prefix}_ffn_fc_0.b_0"], 
            name=f"{tensor_encoder_prefix}{x}/intermediate/dense/bias"))
        tf.Variable(tf.convert_to_tensor(
            params[f"{fluid_prefix}_post_ffn_layer_norm_scale"], 
            name=f"{tensor_encoder_prefix}{x}/output/LayerNorm/gamma"))
        tf.Variable(tf.convert_to_tensor(
            params[f"{fluid_prefix}_post_ffn_layer_norm_bias"], 
            name=f"{tensor_encoder_prefix}{x}/output/LayerNorm/beta"))
        tf.Variable(tf.convert_to_tensor(
            params[f"{fluid_prefix}_ffn_fc_1.w_0"], 
            name=f"{tensor_encoder_prefix}{x}/output/dense/kernel"))
        tf.Variable(tf.convert_to_tensor(
            params[f"{fluid_prefix}_ffn_fc_1.b_0"], 
            name=f"{tensor_encoder_prefix}{x}/output/dense/bias"))
    # Pooler
    tensor_pooler_prefix = f"{tensor_prefix}/pooler"
    tf.Variable(tf.convert_to_tensor(params['pooled_fc.w_0'], name=f"{tensor_pooler_prefix}/dense/kernel"))
    tf.Variable(tf.convert_to_tensor(params['pooled_fc.b_0'], name=f"{tensor_pooler_prefix}/dense/bias"))

    if training:
        # Cls
        tf.Variable(tf.convert_to_tensor(params['mask_lm_out_fc.b_0'], name="cls/predictions/output_bias"))
        tf.Variable(tf.convert_to_tensor(params['mask_lm_trans_layer_norm_scale'], name="cls/predictions/transform/LayerNorm/gamma"))
        tf.Variable(tf.convert_to_tensor(params['mask_lm_trans_layer_norm_bias'], name="cls/predictions/transform/LayerNorm/beta"))
        tf.Variable(tf.convert_to_tensor(params['mask_lm_trans_fc.w_0'], name="cls/predictions/transform/dense/kernel"))
        tf.Variable(tf.convert_to_tensor(params['mask_lm_trans_fc.b_0'], name="cls/predictions/transform/dense/bias"))
        tf.Variable(tf.convert_to_tensor(params['next_sent_fc.w_0'], name="cls/seq_relationship/output_weights"))
        tf.Variable(tf.convert_to_tensor(params['next_sent_fc.b_0'], name="cls/seq_relationship/output_bias"))
        tf.Variable(tf.convert_to_tensor(params['cls_squad_out_w'], name="cls/squad/output_weights"))
        tf.Variable(tf.convert_to_tensor(params['cls_squad_out_b'], name="cls/squad/output_bias"))


def trans_vocab(bert_vocab_path='checkpoints/vocab.txt'):
     with open(args.ernie_vocab_path, 'r', encoding='utf8') as fr:
         with open(bert_vocab_path, 'w', encoding='utf8') as fw:
             for line in fr:
                 word = line.split('\t')[0]
                 fw.write(f"{word}\n")


def add_bert_config(bert_config_path='checkpoints/bert_config.json'):
    bert_config = {
        "attention_probs_dropout_prob": 0.1,
        "directionality": "bidi",
        "hidden_act": "relu",
        "hidden_dropout_prob": 0.1,
        "hidden_size": 768,
        "initializer_range": 0.02,
        "intermediate_size": 3072,
        "max_position_embeddings": 513,
        "num_attention_heads": 12,
        "num_hidden_layers": 12,
        "pooler_fc_size": 768,
        "pooler_num_attention_heads": 12,
        "pooler_num_fc_layers": 3,
        "pooler_size_per_head": 128,
        "pooler_type": "first_token_transform",
        "type_vocab_size": 2,
        "vocab_size": 18000}
    with open(bert_config_path, 'w', encoding='utf8') as f:
        f.write(json.dumps(bert_config))


def save_tensor(paddle_params_np='params.dict'):
    params = joblib.load(paddle_params_np)
    graph = tf.compat.v1.Graph()
    with graph.as_default():
        with tf.compat.v1.Session() as sess:
            convert_np_to_tensor(params)
            saver = tf.compat.v1.train.Saver()
            sess.run(tf.compat.v1.global_variables_initializer())
            with sess.as_default():
                checkpoint_dir = 'checkpoints'
                checkpoint_prefix = os.path.join(checkpoint_dir, 'bert_model.ckpt')
                if not os.path.exists(checkpoint_dir):
                    os.makedirs(checkpoint_dir)
                saver.save(sess, checkpoint_prefix)
            trans_vocab()
            add_bert_config()
    

if __name__ == "__main__":
    convert_paddle_to_np()
    save_tensor()