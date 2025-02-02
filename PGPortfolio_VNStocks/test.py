import torch
import numpy as np
import pandas as pd
import pickle
from matplotlib import pyplot as plt

# You can use the state_tensor_test or reuse the whole state_tensor_train for testing
state_tensor_pf_vnstocks_test = torch.load("data/torch_tensor_vnstocks/state_tensor_pf_vnstocks_test_fullyear.pt")
state_tensor_VNI_test = torch.load("data/torch_tensor_vnstocks/state_tensor_VNI_test_fullyear.pt")

# Load the object from the file using pickle
with open("model_full.pth", "rb") as file:
    agent = torch.load('model_full.pth')
    
agent.actor_network.train(False)
state_tensor_pf = state_tensor_pf_vnstocks_test[:]
state_tensor_bm = state_tensor_VNI_test[:]
lst_actions = [[] for _ in range(state_tensor_pf.shape[2]+1)]
lst_balance_pf = []
lst_balance_bm = []

total_reward = 1
done = 0
prev_w = torch.zeros(1, state_tensor_pf.shape[2], 1, requires_grad=False, dtype=torch.float32)
trans_cost = 0.0015
balance = 10000
pre_each_asset = torch.zeros(1, state_tensor_pf.shape[2]+1, requires_grad=False, dtype=torch.float32)
pre_each_asset[:,-1] = balance
prev_pf = np.array([[balance]])
prev_bm = torch.from_numpy(prev_pf).clone().detach().requires_grad_(False)
prev_pf = torch.from_numpy(prev_pf).clone().detach().requires_grad_(False)
agent.replay_buffer.reset()

with torch.no_grad():
  for i in range(len(state_tensor_pf)-1):
    # Get state tensor
    state_pf = state_tensor_pf[i].unsqueeze(0)
    state_bm = state_tensor_bm[i].unsqueeze(0)
    next_state_pf = state_tensor_pf[i+1].unsqueeze(0)
    next_state_bm = state_tensor_bm[i+1].unsqueeze(0)
    
    if i%agent.rebalance_period==0:
      # Calculate actions
      action_stocks, action_pf = agent.policy.select_action(state_pf, prev_w)

      # Re-calculate portfolio after new allocation
      post_each_asset = action_pf.squeeze(2) * prev_pf
      transaction_amount = post_each_asset - pre_each_asset
      transaction_cost_for_each = torch.abs(transaction_amount) * trans_cost
      post_each_asset[:,-1] -= torch.sum(transaction_cost_for_each, 1) - transaction_cost_for_each[:,-1]
      prev_pf_after_transaction = torch.sum(post_each_asset, 1)
      prev_cash = post_each_asset[:,-1].unsqueeze(0)
      prev_stocks = prev_pf_after_transaction - prev_cash
      action_stocks = (post_each_asset / prev_pf_after_transaction)[:,:state_tensor_pf.shape[2]].unsqueeze(-1)
      action_pf = (post_each_asset / prev_pf_after_transaction).unsqueeze(-1)

      # Calculate the reward of the action - Daily return
      ret = 1 / next_state_pf[:,0,:,-2].unsqueeze(2)
      tot_ret = ret * post_each_asset[:,:state_tensor_pf.shape[2]].unsqueeze(-1)
      new_pf = torch.sum(tot_ret.squeeze(-1),-1) + post_each_asset[:,-1].unsqueeze(-1)
      ret_pf = (new_pf - prev_pf_after_transaction) / prev_pf_after_transaction
      ret_bench = 1/next_state_bm[:,0,:,-2]
      post_each_asset[:,:-1] = tot_ret.squeeze(-1)
    else:
      action_stocks = (pre_each_asset / prev_pf)[:,:state_tensor_pf.shape[2]].unsqueeze(-1)
      action_pf = (pre_each_asset / prev_pf).unsqueeze(-1)
      
      # Calculate the reward of the action - Daily return
      ret = 1 / next_state_pf[:,0,:,-2].unsqueeze(2)
      tot_ret = ret * pre_each_asset[:,:state_tensor_pf.shape[2]].unsqueeze(-1)
      new_pf = torch.sum(tot_ret.squeeze(-1),-1) + pre_each_asset[:,-1].unsqueeze(-1)
      ret_pf = (new_pf - prev_pf) / prev_pf
      ret_bench = 1/next_state_bm[:,0,:,-2]
      post_each_asset[:,:-1] = tot_ret.squeeze(-1)

    # Calculate the reward
    new_bm = prev_bm * ret_bench
    reward = (ret_pf+1) - ret_bench
    balance = new_pf.clone().detach().requires_grad_(False).squeeze(0).numpy()
    prev_pf = new_pf
    prev_bm = new_bm.unsqueeze(0)
    pre_each_asset = post_each_asset
    total_reward *= (1+reward.item())

    # Keep track the actions for later visualization
    for n in range(state_tensor_pf.shape[2]+1):
      lst_actions[n].append(action_pf.squeeze(0).squeeze(1)[n].clone().detach().requires_grad_(False).item())

    prev_w = action_stocks
    lst_balance_pf.append(balance.item())
    lst_balance_bm.append(new_bm.item())
    print(f"Transaction cost: {torch.sum(transaction_cost_for_each, 1) - transaction_cost_for_each[:,-1]}")
    print(f"Time step {i + 1}, Reward: {reward.item()}, Total Balance: {balance.item()}, Benchmark: {new_bm.item()}")
    print("------------------------------------------------------")

# Visualization of the allocation during period of testing
s, e = 0, -1
vn_symbols = [
    'ACB',
    'BID',
    'BVH',
    'CTG',
    'FPT',
    'HPG',
    'MBB',
    'MSN',
    'MWG',
    "SSI",
    "STB",
    "VCB",
    "VIC",
    "VNM",
]
chosen_symbols=vn_symbols
for i in range(len(lst_actions)):
  if i!=len(lst_actions)-1:
    plt.plot(lst_actions[i][s:e], label=chosen_symbols[i])
  else:
    plt.plot(lst_actions[i][s:e], label="Cash")
plt.legend(loc='upper left', bbox_to_anchor=(1, 1))
plt.title("The allocation track by PGPortfolio for the full year of 2023")
plt.xlabel("Time steps")
plt.ylabel("Portfolio weights")
plt.savefig('The allocation track by PGPortfolio for the full year of 2023.png') 
plt.show()

# Visualization of the agent performance relative to the benchmark
bm = "VNI"
plt.plot(lst_balance_pf, label="Price")
plt.plot(lst_balance_bm, label=bm)
plt.title(f"Balance track of My Agent and {bm} for testing dataset")
plt.legend()
plt.savefig(f"Balance track of My Agent and {bm} for testing dataset")
plt.show()

df_performance = pd.DataFrame()
df_performance["Price"] = pd.Series([10000] + lst_balance_pf)
df_performance[bm] = pd.Series([10000] + lst_balance_bm)
df_performance.to_csv("utils/df_performance.csv")

