# reBot Bimanual Guide: RS / DM Calibration, Teleoperation, Data Collection, and Training

## 2.

Before using both arms, set up the environment by following the single-arm getting started guides:

- <https://wiki.seeedstudio.com/cn/rebot_b601_rs_getting_started/>
- <https://wiki.seeedstudio.com/cn/rebot_arm_b601_rs_lerobot/>

### 2.1 Activate the Existing Environment

```bash
conda activate lerobot

cd ~
git clone https://github.com/xiehuangbao888/lerobot-robot-seeed-b601.git
cd lerobot-robot-seeed-b601
pip install -e .
```

### 2.2 Port Assignments Used in This Guide

| Device | Left | Right |
| --- | --- | --- |
| Arm 102 leader | `/dev/ttyUSB0` | `/dev/ttyUSB1` |
| RS follower | `can0` | `can1` |
| DM follower, Damiao serial adapter | `/dev/ttyACM0` | `/dev/ttyACM1` |

## 3. Bimanual Calibration

Use the same `robot.id` and `teleop.id` for calibration and all subsequent operations. Both the RS and DM examples use `bi_follower`, and the two leaders use `bi_leader`. The `id` identifies calibration files, not the motor model. If you previously calibrated your DM arms with `bi_follower_dm`, keep using `bi_follower_dm` in subsequent commands for those arms.

### 3.1 Calibrate Two RS Followers

**RS**

**left**

```bash
sudo ip link set can0 down 2>/dev/null
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
```

**right**

```bash
sudo ip link set can1 down 2>/dev/null
sudo ip link set can1 type can bitrate 1000000
sudo ip link set can1 up
```

```bash
lerobot-calibrate \
    --robot.type=bi_seeed_b601_follower \
    --robot.id=bi_follower \
    --robot.left_arm_config.motor_family=rs \
    --robot.left_arm_config.port=can0 \
    --robot.right_arm_config.motor_family=rs \
    --robot.right_arm_config.port=can1
```

### 3.2 Calibrate Two DM Followers: Damiao Serial Adapters

```bash
sudo chmod 666 /dev/ttyACM*
```

```bash
lerobot-calibrate \
    --robot.type=bi_seeed_b601_follower \
    --robot.id=bi_follower \
    --robot.left_arm_config.motor_family=dm \
    --robot.left_arm_config.port=/dev/ttyACM0 \
    --robot.right_arm_config.motor_family=dm \
    --robot.right_arm_config.port=/dev/ttyACM1
```

### 3.3 Calibrate Both Leaders

```bash
lerobot-calibrate \
    --teleop.type=bi_seeed_102_leader \
    --teleop.id=bi_leader \
    --teleop.left_arm_config.port=/dev/ttyUSB0 \
    --teleop.right_arm_config.port=/dev/ttyUSB1
```

### 3.4 Calibration Procedure

1. Follow the prompts to calibrate the left and right arms in order.
2. If calibration already exists, press Enter to reuse it, or type `c` and press Enter to recalibrate.
3. When prompted to position the arm manually at zero, place the entire arm in the specified zero pose, fully close the empty gripper, and then confirm.
4. Follower calibration resets the zero positions of all motors in the arm, not just the gripper. Do not confirm zeroing while the arm is in an arbitrary pose.

Exiting calibration does not trigger automatic parking of the two arms. Calibration files are stored under `~/.cache/huggingface/lerobot/calibration/` by default, in subdirectories for the underlying device types. Each side adds `_left` or `_right` to its ID. Recheck calibration after replacing a physical arm or changing motor zero positions.

## 4. Bimanual Teleoperation

### 4.1 Teleoperate Two RS Arms

```bash
lerobot-teleoperate \
    --robot.type=bi_seeed_b601_follower \
    --robot.id=bi_follower \
    --robot.left_arm_config.motor_family=rs \
    --robot.left_arm_config.port=can0 \
    --robot.right_arm_config.motor_family=rs \
    --robot.right_arm_config.port=can1 \
    --teleop.type=bi_seeed_102_leader \
    --teleop.id=bi_leader \
    --teleop.left_arm_config.port=/dev/ttyUSB0 \
    --teleop.right_arm_config.port=/dev/ttyUSB1 \
```

### 4.2 Teleoperate Two DM Arms: Damiao Serial Adapters

```bash
lerobot-teleoperate \
    --robot.type=bi_seeed_b601_follower \
    --robot.id=bi_follower \
    --robot.left_arm_config.motor_family=dm \
    --robot.left_arm_config.port=/dev/ttyACM0 \
    --robot.right_arm_config.motor_family=dm \
    --robot.right_arm_config.port=/dev/ttyACM1 \
    --teleop.type=bi_seeed_102_leader \
    --teleop.id=bi_leader \
    --teleop.left_arm_config.port=/dev/ttyUSB0 \
    --teleop.right_arm_config.port=/dev/ttyUSB1 \
```

## 6. Data Collection

Verify that teleoperation works before running the recording commands. The examples below record two episodes of 20 seconds each, only to check the data collection workflow. Change `dataset.single_task` to describe the task you are demonstrating.

### 6.1 Two RS Arms: Recording with Three Cameras

```bash
lerobot-record \
    --robot.type=bi_seeed_b601_follower \
    --robot.id=bi_follower \
    --robot.left_arm_config.motor_family=rs \
    --robot.left_arm_config.port=can0 \
    --robot.right_arm_config.motor_family=rs \
    --robot.right_arm_config.port=can1 \
    --robot.cameras='{
      top: {
        type: opencv,
        index_or_path: "/dev/video0",
        width: 640,
        height: 480,
        fps: 30,
        fourcc: "MJPG"
      },
      left_wrist: {
        type: opencv,
        index_or_path: "/dev/video2",
        width: 640,
        height: 480,
        fps: 30,
        fourcc: "MJPG"
      },
      right_wrist: {
        type: opencv,
        index_or_path: "/dev/video4",
        width: 640,
        height: 480,
        fps: 30,
        fourcc: "MJPG"
      }
    }' \
    --teleop.type=bi_seeed_102_leader \
    --teleop.id=bi_leader \
    --teleop.left_arm_config.port=/dev/ttyUSB0 \
    --teleop.right_arm_config.port=/dev/ttyUSB1 \
    --dataset.repo_id=seeed_rebot/test \
    --dataset.single_task="pick the cube" \
    --dataset.fps=30 \
    --dataset.num_episodes=2 \
    --dataset.episode_time_s=20 \
    --dataset.reset_time_s=10 \
    --dataset.push_to_hub=false \
    --display_data=false
```

### 6.2 Two DM Arms: Damiao Serial Adapters and Three Cameras

```bash
lerobot-record \
    --robot.type=bi_seeed_b601_follower \
    --robot.id=bi_follower \
    --robot.left_arm_config.motor_family=dm \
    --robot.left_arm_config.port=/dev/ttyACM0 \
    --robot.right_arm_config.motor_family=dm \
    --robot.right_arm_config.port=/dev/ttyACM1 \
    --robot.cameras='{
      top: {
        type: opencv,
        index_or_path: "/dev/video0",
        width: 640,
        height: 480,
        fps: 30,
        fourcc: "MJPG"
      },
      left_wrist: {
        type: opencv,
        index_or_path: "/dev/video2",
        width: 640,
        height: 480,
        fps: 30,
        fourcc: "MJPG"
      },
      right_wrist: {
        type: opencv,
        index_or_path: "/dev/video4",
        width: 640,
        height: 480,
        fps: 30,
        fourcc: "MJPG"
      }
    }' \
    --teleop.type=bi_seeed_102_leader \
    --teleop.id=bi_leader \
    --teleop.left_arm_config.port=/dev/ttyUSB0 \
    --teleop.right_arm_config.port=/dev/ttyUSB1 \
    --dataset.repo_id=seeed_rebot/test \
    --dataset.single_task="pick the cube" \
    --dataset.fps=30 \
    --dataset.num_episodes=2 \
    --dataset.episode_time_s=20 \
    --dataset.reset_time_s=10 \
    --dataset.push_to_hub=false \
    --display_data=false
```

## 8. ACT Training
### 8.1 Start Training

The recording commands above append a timestamp to the dataset name by default. Replace `seeed_rebot/test_20261118_160000` in the example below with the actual full dataset name. You can find it under `/home/zy/.cache/huggingface/lerobot/seeed_rebot/`.

```bash
lerobot-train \
    --dataset.repo_id=seeed_rebot/test_20261118_160000 \
    --dataset.video_backend=pyav \
    --policy.type=act \
    --output_dir=/home/zy/lerobot_outputs/act_bimanual_test \
    --job_name=act_bimanual_test \
    --policy.device=cuda \
    --policy.push_to_hub=false \
    --trackio.enable=false \
    --batch_size=8 \
    --steps=300000
```

- `cuda` requires an available NVIDIA GPU. If GPU memory is insufficient, reduce `batch_size` to `4` or `2`.
- The current version uses `trackio.enable` instead of the older `wandb.enable` parameter shown in the tutorial.
- For a new training run, use an `output_dir` that does not already exist. Use different output directories when training separately on RS and DM data.

### 8.2 Model Checkpoints and Resuming Training

By default, checkpoints are saved every 20000 steps and at the end of training. The latest model is stored in:

```text
/home/zy/lerobot_outputs/act_bimanual_test/checkpoints/last/pretrained_model
```

If training is interrupted, resume from the most recently saved checkpoint:

```bash
lerobot-train \
    --config_path=/home/zy/lerobot_outputs/act_bimanual_test/checkpoints/last/pretrained_model/train_config.json \
    --resume=true \
    --steps=300000
```

`steps` specifies the target total number of steps, not the number of additional steps. If you changed the output directory, update the path in the resume command accordingly.
