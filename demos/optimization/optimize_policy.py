# global
import ivy_gym
import argparse
import numpy as np
from ivy_demo_utils.framework_utils import choose_random_framework, get_framework_from_str


class Policy:

    def __init__(self, in_size, out_size, f):

        # framework
        self._f = f

        # weights
        w0lim = (6 / (64 + in_size)) ** 0.5
        w0 = f.variable(f.random_uniform(-w0lim, w0lim, (64, in_size)))
        w1lim = (6 / (64 + 64)) ** 0.5
        w1 = f.variable(f.random_uniform(-w1lim, w1lim, (64, 64)))
        w2lim = (6 / (out_size + 64)) ** 0.5
        w2 = f.variable(f.random_uniform(-w2lim, w2lim, (out_size, 64)))

        # biases
        b0 = f.variable(f.zeros((64,)))
        b1 = f.variable(f.zeros((64,)))
        b2 = f.variable(f.zeros((out_size,)))

        # variables
        self.variables = [w0, w1, w2, b0, b1, b2]

    def call(self, x, variables=None):
        x = self._f.expand_dims(x, 0)
        if variables is not None:
            v = variables
        else:
            v = self.variables
        x = self._f.nn.tanh(self._f.nn.linear(x, v[0], v[3]))
        x = self._f.nn.tanh(self._f.nn.linear(x, v[1], v[4]))
        return self._f.nn.tanh(self._f.nn.linear(x, v[2], v[5]))[0]


def loss_fn(env, initial_state, policy_callable, steps, f):
    obs = env.set_state(initial_state)
    score = f.array([0.])
    for step in range(steps):
        ac = policy_callable(obs)
        obs, rew, _, _ = env.step(ac)
        score = score + rew
    return -score[0]


def train_step(compiled_loss_fn, initial_state, policy, lr, f):
    loss, grads = f.execute_with_gradients(lambda pol_vs: compiled_loss_fn(initial_state, pol_vs), policy.variables)
    policy.variables = f.gradient_descent_update(policy.variables, grads, lr)
    return -f.reshape(loss, (1,))


def main(env_str, steps=100, iters=10000, lr=0.001, seed=0, log_freq=100, vis_freq=1000, visualize=True, f=None):

    # config
    f = choose_random_framework(excluded=['numpy']) if f is None else f
    f.seed(seed)
    env = getattr(ivy_gym, env_str)(f=f)
    starting_obs = env.reset()

    # policy
    in_size = starting_obs.shape[0]
    ac_dim = env.action_space.shape[0]
    policy = Policy(in_size, ac_dim, f)

    # compile loss function
    compiled_loss_fn = f.compile_fn(lambda initial_state, pol_vs:
                                    loss_fn(env, initial_state, lambda x: policy.call(x, pol_vs), steps, f),
                                    example_inputs=[env.get_state(), policy.variables])

    # Train
    scores = []
    for iteration in range(iters):

        if iteration % vis_freq == 0 and visualize:
            obs = env.reset()
            env.render()
            for _ in range(steps):
                ac = policy.call(obs)
                obs, _, _, _ = env.step(ac)
                env.render()

        env.reset()
        if iteration == 0:
            print('\nCompiling loss function for {} environment steps... This may take a while...\n'.format(steps))
        score = train_step(compiled_loss_fn, env.get_state(), policy, lr, f)
        if iteration == 0:
            print('\nLoss function compiled!\n')
        print('iteration {} score {}'.format(iteration, f.to_numpy(score).item()))
        scores.append(f.to_numpy(score)[0])

        if len(scores) == log_freq:
            print('\nIterations: {} Mean Score: {}\n'.format(iteration + 1, np.mean(scores)))
            scores.clear()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--no_visuals', action='store_true',
                        help='whether to run the demo without rendering images.')
    parser.add_argument('--env', default='CartPole',
                        choices=['CartPole', 'Pendulum', 'MountainCar', 'Reacher', 'Swimmer'])
    parser.add_argument('--framework', type=str, default=None,
                        help='which framework to use. Chooses a random framework if unspecified.')
    parser.add_argument('--steps', type=int, default=100)
    parser.add_argument('--iters', type=int, default=10000)
    parser.add_argument('--lr', type=float, default=0.001)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--log_freq', type=int, default=100)
    parser.add_argument('--vis_freq', type=int, default=1000)
    parsed_args = parser.parse_args()
    framework = get_framework_from_str(parsed_args.framework)
    if parsed_args.framework == 'numpy':
        raise Exception('Invalid framework selection. Numpy does not support auto-differentiation.\n'
                        'This demo involves gradient-based optimization, and so auto-diff is required.\n'
                        'Please choose a different backend framework.')
    print('\nTraining for {} iterations.\n'.format(parsed_args.iters))
    main(parsed_args.env, parsed_args.steps, parsed_args.iters, parsed_args.lr, parsed_args.seed,
         parsed_args.log_freq, parsed_args.vis_freq, not parsed_args.no_visuals, framework)