from .main import Repository
from .pull_req_state import PullReqState
import time


def resynchronize_thread(g):
    while True:
        for repo_label in g.repo_cfgs:
            resynchronize(repo_label, g.repo_cfgs[repo_label], g.logger, g.gh, g.states, g.repos, g.db, g.mergeable_que, g.my_username, g.repo_labels) # noqa
        print()
        time.sleep(5 * 60)


def resynchronize(repo_label, repo_cfg, logger, gh, states, repos, db, mergeable_que, my_username, repo_labels):  # noqa
    logger.info('Synchronizing {}...'.format(repo_label))

    repo = gh.repository(repo_cfg['owner'], repo_cfg['name'])
    ghv4 = gh.v4

    saved_states = {}
    for num, state in states[repo_label].items():
        saved_states[num] = {
            'merge_sha': state.merge_sha,
            'build_res': state.build_res,
        }

    if repo_label not in states:
        states[repo_label] = {}
        repos[repo_label] = Repository(repo, repo_label, db)

    seen_existing_states = {}
    for number in states[repo_label]:
        seen_existing_states[number] = False

    try:
        pulls = ghv4.pull_requests(repo_cfg['owner'], repo_cfg['name'])
    except Exception as e:
        print("Failed to get pulls: {}".format(e))
        return

    for pull in pulls:
        state = states[repo_label].get(pull.number, None)
        seen_existing_states[pull.number] = True

        if state is None:
            print("{}/{}#{} from beginning".format(repo_cfg['owner'], repo_cfg['name'], pull.number)) # noqa
            try:
                response = ghv4.pull_request(
                        repo_cfg['owner'],
                        repo_cfg['name'],
                        pull.number)
            except Exception as e:
                print("Failed {}/{}#{}: {}".format(
                    repo_cfg['owner'],
                    repo_cfg['name'],
                    pull.number,
                    e))
                continue
            status = ''

            state = PullReqState(pull.number, pull.head_sha, status, db, repo_label, mergeable_que, gh, repo_cfg['owner'], repo_cfg['name'], repo_cfg.get('labels', {}), repos)  # noqa
            state.cfg = repo_cfg
            state.title = response.initial_title
            state.body = pull.body
            state.head_ref = pull.head_ref
            state.base_ref = pull.base_ref
            if response.mergeable == 'MERGEABLE':
                state.set_mergeable(True)
            elif response.mergeable == 'CONFLICTING':
                state.set_mergeable(False)
            else:
                state.set_mergeable(None)
            state.assignee = ''

        else:
            if state.last_github_cursor == pull.timeline_cursor:
                #print("{}/{}#{} is up-to-date".format(repo_cfg['owner'], repo_cfg['name'], pull.number)) # noqa
                continue

            print("{}/{}#{} from {} because its cursor differs".format(repo_cfg['owner'], repo_cfg['name'], pull.number, state.last_github_cursor)) # noqa
            try:
                response = ghv4.pull_request(
                        repo_cfg['owner'],
                        repo_cfg['name'],
                        pull.number,
                        state.last_github_cursor)
            except Exception as e:
                print("{}/{}#{} failed: {}".format(
                    repo_cfg['owner'],
                    repo_cfg['name'],
                    pull.number,
                    e))
                continue

        for event in response.events:
            state.process_event(event)

        states[repo_label][pull.number] = state

    for pull_number in seen_existing_states:
        seen = seen_existing_states[pull_number]
        if seen:
            continue

        state = states[repo_label].get(pull_number, None)
        if state is None:
            continue

        print("{}/{}#{} from {} because it is no longer in the OPEN list".format(repo_cfg['owner'], repo_cfg['name'], pull_number, state.last_github_cursor)) # noqa
        try:
            response = ghv4.pull_request(
                    repo_cfg['owner'],
                    repo_cfg['name'],
                    pull.number,
                    state.last_github_cursor)
        except Exception as e:
            print("Failed {}/{}#{}: {}".format(
                repo_cfg['owner'],
                repo_cfg['name'],
                pull.number,
                e))
            continue

        for event in response.events:
            state.process_event(event)

        states[repo_label][pull.number] = state

#    logger.info('Done synchronizing {}!'.format(repo_label))
