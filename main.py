import collections
import sys
import os
import warnings
import argparse
from time import localtime, strftime
import torch
from utils.plot import *
from utils.utils import *
from model.model import DrlDbscan

"""
    Training and testing DRL-DBSCAN.
    Paper: Automating DBSCAN via Reinforcement Learning
    Source: https://anonymous.4open.science/r/DRL-DBSCAN
"""

parser = argparse.ArgumentParser()

# Shape-Pathbased.txt, Shape-Compound.txt, Shape-Aggregation.txt, Shape-D31.txt Stream-Sensor.txt
parser.add_argument('--data_path', default='data/Shape-Pathbased.txt', type=str,
                    help="Path of features and labels")
parser.add_argument('--log_path', default='results/test', type=str,
                    help="Path of results")

# Model dependent args
parser.add_argument('--use_cuda', default=False, action='store_true',
                    help="Use cuda")
parser.add_argument('--train_size', default=0.20, type=float,
                    help="Sample size used to get rewards")
parser.add_argument('--episode_num', default=15, type=int,
                    help="The number of episode")   # Pre-training and Maintenance: 50
parser.add_argument('--block_num', default=1, type=int,
                    help="The number of data blcoks")  # Offline: 1, Online: 16
parser.add_argument('--block_size', default=5040, type=int,
                    help="The size of data block")  # Offline: -, Online: 5040
parser.add_argument('--layer_num', default=6, type=int,
                    help="The number of recursive layer")  # Offline: 3, Online: 6
parser.add_argument('--eps_size', default=10, type=int,
                    help="Eps parameter space size")
parser.add_argument('--min_size', default=4, type=int,
                    help="MinPts parameter space size")
parser.add_argument('--reward_factor', default=0.2, type=float,
                    help="The impact factor of reward")

# TD3 args
parser.add_argument('--device', default="cpu", type=str,
                    help='"cuda" if torch.cuda.is_available() else "cpu".')
parser.add_argument('--batch_size', default=32, type=int,
                    help='"Reinforcement learning for sampling batch size')
parser.add_argument('--step_num', default=30, type=int,
                    help="Maximum number of steps per RL game")

# Shraban Arguments
parser.add_argument('--tweet_block', default=1, type=int,
                    help='Which tweet block to run the clusterering algorithm on')

parser.add_argument('--methodology', default='finevent', type=str,
                    help='spacy or finevent or unsupervised')



if __name__ == '__main__':

    print('\n+-------------------------------------------------------+\n'
          '* Training and testing DRL-DBSCAN *\n'
          '* Paper: Automating DBSCAN via Reinforcement Learning *\n'
          '* Source: https://anonymous.4open.science/r/DRL-DBSCAN *\n'
          '\n+-------------------------------------------------------+\n'
          )
    # load hyper-parameters
    args = parser.parse_args()

    # generate log folder
    time_log = '/log_' + strftime("%m%d%H%M%S", localtime())
    log_save_path = args.log_path + time_log
    os.mkdir(log_save_path)
    print("Log save path:  ", log_save_path, flush=True)

    # standardize output records and ignore warnings
    warnings.filterwarnings('ignore')
    std = open(log_save_path + '/std.log', 'a')
    sys.stdout = std
    sys.stderr = std

    # CUDA
    use_cuda = args.use_cuda and torch.cuda.is_available()
    print("Using CUDA:  " + str(use_cuda), flush=True)
    print("Running on:  " + str(args.data_path), flush=True)

    # get sample serial numbers for rewards, out-of-order data features and labels
    if "Shape" in args.data_path:
        idx_reward, features, labels = load_data_shape(args.data_path, args.train_size, args.tweet_block, args.methodology)
        idx_reward, features, labels = [idx_reward], [features], [labels]
    elif "Stream" in args.data_path:
        idx_reward, features, labels = load_data_stream(args.data_path, args.train_size,
                                                        args.block_num, args.block_size)

    # generate parameter space size, step size, starting point of the first layer, limit bound
    print("Train size:  " + str(args.train_size), flush=True)
    p_size, p_step, p_center, p_bound = generate_parameter_space(features[0], args.layer_num,
                                                                 args.eps_size, args.min_size,
                                                                 args.data_path)

    # build a multi-layer agent collection, each layer has an independent agent
    agents = []
    for l in range(0, args.layer_num):
        drl = DrlDbscan(p_size, p_step[l], p_center, p_bound, args.device, args.batch_size,
                        args.step_num, features[0].shape[1])
        agents.append(drl)

    # Train agents with serialized data blocks
    b = str(args.tweet_block) + '_' + args.methodology # Replace b1 with b for original code and delete this line
    for b1 in range(0, args.block_num):
        # log path
        if not os.path.exists(args.log_path + '/Block' + str(b)):
            os.mkdir(args.log_path + '/Block' + str(b))
        os.mkdir(args.log_path + '/Block' + str(b) + time_log)
        std = open(args.log_path + '/Block' + str(b) + time_log + '/std.log', 'a')
        sys.stdout = std
        sys.stderr = std

        # compare with the result of Kmeans
        k_nmi, k_ami, k_ari = kmeans_metrics(features[b1], labels[b1])
        with open(args.log_path + '/Block' + str(b) + '/k_nmi.txt', 'w') as f:
            f.write(str(k_nmi))
        with open(args.log_path + '/Block' + str(b) + '/k_ami.txt', 'w') as f:
            f.write(str(k_ami))
        with open(args.log_path + '/Block' + str(b) + '/k_ari.txt', 'w') as f:
            f.write(str(k_ari))

        final_reward_test = [0, p_center, 0]
        label_dic_test = set()

        # test each layer agent
        for l in range(0, args.layer_num):
            agent = agents[l]
            print("[ Testing Layer {0} ]".format(l), flush=True)

            # update starting point
            print("Resetting the parameter space......", flush=True)
            agent.reset(final_reward_test)

            # testing
            cur_labels, cur_cluster_num, p_log = agent.detect(features[b1], collections.OrderedDict())
            final_reward_test = [0, p_log[-1], 0]
            d_nmi, d_ami, d_ari = dbscan_metrics(labels[b1], cur_labels)

            # update log
            for p in p_log:
                label_dic_test.add(str(p[0]) + str("+") + str(p[1]))
        with open(args.log_path + '/Block' + str(b) + '/0_test.txt', 'a') as f:
            f.write(str(d_nmi) + "," + str(d_ami) + "," + str(d_ari) + "," +
                    str(final_reward_test[1]) + "," + str(cur_cluster_num) + "," + str(len(label_dic_test)) + '\n')

        max_max_reward = [0, p_center, 0]
        max_reward = [0, p_center, 0]
        label_dic = collections.OrderedDict()
        first_meet_num = 0

        # train each layer agent
        for l in range(0, args.layer_num):
            agent = agents[l]
            agent.reset(max_max_reward)
            max_max_reward_logs = [max_max_reward[0]]
            early_stop = False
            his_hash_size = len(label_dic)
            cur_hash_size = len(label_dic)
            for i in range(1, args.episode_num):
                print('\n+---------------------------------------------------------------+\n'
                      '                Block {0}, Layer {1}, Episode {2}                    '
                      '\n+---------------------------------------------------------------+\n'.format(b, l, i)
                      )

                # begin training process
                print(len(label_dic))
                print("[ Training Layer {0} ]".format(l), flush=True)
                print("The size of Label Hash is: {0}".format(len(label_dic)), flush=True)
                p_logs = np.array([[], []])
                nmi_logs = np.array([])

                # update starting point
                print("Resetting the parameter space......", flush=True)
                agent.reset0()

                # train the l-th layer
                print("Training the {0}-th layer agent......".format(l), flush=True)
                cur_labels, cur_cluster_num, p_log, nmi_log, max_reward = agent.train(i, idx_reward[b1], features[b1],
                                                                                      labels[b1], label_dic,
                                                                                      args.reward_factor)

                # update log
                p_logs = np.hstack((p_logs, np.array(list(zip(*p_log)))))
                nmi_logs = np.hstack((nmi_logs, np.array(nmi_log)))
                d_nmi, d_ami, d_ari = dbscan_metrics(labels[b1], cur_labels)
                with open(args.log_path + '/Block' + str(b) + time_log + '/init_log.txt', 'a') as f:
                    f.write('episode=' + str(i) + ', layer=' + str(l) + ',K-Means NMI=' + str(k_nmi) + '\n')
                    f.write(str(p_logs) + '\n')
                    f.write(str(nmi_logs) + '\n')
                if max_max_reward[0] < max_reward[0]:
                    max_max_reward = list(max_reward)
                    cur_hash_size = len(label_dic)
                max_max_reward_logs.append(max_max_reward[0])

                # test each layer agent once again
                print('~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n', flush=True)
                print("[ Testing Layer {0} ]".format(l), flush=True)

                # update starting point
                print("Resetting the parameter space......", flush=True)
                agent.reset0()
                cur_labels, cur_cluster_num, p_log = agent.detect(features[b1], label_dic)
                d_nmi, d_ami, d_ari = dbscan_metrics(labels[b1], cur_labels)

                # early stop
                if len(max_max_reward_logs) > 3 and \
                        max_max_reward_logs[-1] == max_max_reward_logs[-2] == max_max_reward_logs[-3] and \
                        max_max_reward_logs[-1] != max_max_reward_logs[0]:
                    break
            first_meet_num += cur_hash_size - his_hash_size
            if cur_hash_size == his_hash_size:
                print("......Early stop at layer {0}......".format(l), flush=True)
                break

        print('~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n', flush=True)
        print('~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n', flush=True)
        print("Final Results: ", flush=True)
        print("[ Total Hash Size is {0} ]".format(len(label_dic)), flush=True)
        print("[ The best parameter is {0} ]".format(max_max_reward[1]), flush=True)
        print("[ The best parameter appears at {0} ]".format(first_meet_num), flush=True)
        cur_labels = label_dic[str(max_max_reward[1][0]) + str("+") + str(max_max_reward[1][1])]
        cur_cluster_num = len(set(list(cur_labels)))
        print("[ The number of clusters is {0} ]".format(cur_cluster_num), flush=True)
        nmi, ami, ari = dbscan_metrics(labels[b1], cur_labels)
        print('~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n', flush=True)
        print('~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n', flush=True)

        with open(args.log_path + '/Block' + str(b) + '/1_nmi.txt', 'a') as f:
            f.write(str(nmi) + '\n')
        with open(args.log_path + '/Block' + str(b) + '/2_ami.txt', 'a') as f:
            f.write(str(ami) + '\n')
        with open(args.log_path + '/Block' + str(b) + '/3_ari.txt', 'a') as f:
            f.write(str(ari) + '\n')
        with open(args.log_path + '/Block' + str(b) + '/4_eps.txt', 'a') as f:
            f.write(str(max_max_reward[1][0]) + '\n')
        with open(args.log_path + '/Block' + str(b) + '/5_min_samples.txt', 'a') as f:
            f.write(str(max_max_reward[1][1]) + '\n')
        with open(args.log_path + '/Block' + str(b) + '/6_cur_cluster_num.txt', 'a') as f:
            f.write(str(cur_cluster_num) + '\n')
        with open(args.log_path + '/Block' + str(b) + '/7_first_num.txt', 'a') as f:
            f.write(str(first_meet_num) + '\n')
        with open(args.log_path + '/Block' + str(b) + '/8_all_num.txt', 'a') as f:
            f.write(str(len(label_dic)) + '\n')
        
        torch.save(cur_labels,args.log_path + '/Block' + str(b) + '/9_pred_cluster_label.pt')
        torch.save(labels[b1],args.log_path + '/Block' + str(b) + '/10_actual_cluster_label.pt')

        # evaluate clustering result
        max_reward_nmi = 0
        max_nmi = 0
        max_nmi_logs = []
        for cur_labels in label_dic.values():
            reward_nmi = metrics.normalized_mutual_info_score(labels[b1][idx_reward[b1]], cur_labels[idx_reward[b1]])
            nmi = metrics.normalized_mutual_info_score(labels[b1], cur_labels)
            if reward_nmi > max_reward_nmi:
                max_reward_nmi, max_nmi = reward_nmi, nmi
            max_nmi_logs.append(max_nmi)
        get_nmi_fig(log_save_path, max_nmi_logs, k_nmi, num="max_nmi_logs")
        with open(args.log_path + '/Block' + str(b) + '/max_nmi_logs.txt', 'a') as f:
            f.write(str(max_nmi_logs) + '\n')



