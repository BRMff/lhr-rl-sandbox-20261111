"""Release gate tests (RL-U*). Synthetic repository model; no network."""

import base64
import copy
import inspect
import unittest

from tests.governance_support import BOT, OWNER, REPO, github_api, release_gate as rel, sha, ts

C00, C0, C1, C2, C3, C4, OFF = (sha(n) for n in (0x100, 0x101, 0x102, 0x103, 0x104, 0x105, 0x1FF))
H5 = sha(0x205)
GATE_FILES = (".github/workflows/review-gate.yml", ".github/workflows/release-gate.yml")


def b64(text):
    return {"encoding": "base64", "content": base64.b64encode(text.encode()).decode()}


class FakeRepo:
    def __init__(self):
        self.head = C3
        self.parents = {C00: [], C0: [C00], C1: [C0], C2: [C1], C3: [C2], C4: [C3], OFF: [C3]}
        self.files = {}
        for commit in (C2, C3, C4, OFF):
            for path in GATE_FILES:
                self.files[(path, commit)] = "workflow"
        for commit in (C00, C0, C1, C2, C3, C4, OFF):
            self.files[("linux_health_reporter/__init__.py", commit)] = '__version__ = "0.3.0"\n'
            self.files[("CHANGELOG.md", commit)] = "# Changelog\n\n## [0.3.0] — 2026-11-10\n"
        self.tags = {"v0.1.0": {"type": "commit", "sha": C00}, "v0.2.0": {"type": "commit", "sha": C0}}
        self.annotated = {}
        self.check_runs = {c: [self.run_check(name, i) for i, name in enumerate(rel.MAIN_REQUIRED_CHECKS)]
                           for c in (C0, C1, C2, C3, C4, OFF)}
        self.pulls = {
            C1: [self.pr(2, C1, sha(0x202))],
            C2: [self.pr(4, C2, sha(0x204))],
            C3: [self.pr(5, C3, H5)],
            C4: [self.pr(6, C4, sha(0x206))],
        }
        self.statuses = {
            H5: [self.status("review-gate", "success", 50)],
            sha(0x206): [self.status("review-gate", "success", 60)],
            C3: [self.status("release-preflight/v0.3.0", "success", 100, url_run=500)],
        }
        self.runs = {
            500: {"id": 500, "path": ".github/workflows/release-gate.yml", "event": "workflow_dispatch",
                  "head_branch": "main", "head_sha": C3, "conclusion": "success",
                  "display_title": f"release-preflight v0.3.0 {C3}", "created_at": ts(90)},
            600: {"id": 600, "created_at": ts(200), "head_branch": "v0.3.0"},
        }
        self.tag_runs = {"v0.3.0": [self.runs[600]]}
        self.fail = set()
        self.writes = []
        self.api_calls = 0

    @staticmethod
    def run_check(name, i, conclusion="success", status="completed", app="github-actions"):
        return {"id": 1000 + i, "name": name, "status": status, "conclusion": conclusion, "app": {"slug": app}}

    @staticmethod
    def pr(number, merge, head):
        return {"number": number, "merge_commit_sha": merge, "merged_at": ts(1), "base": {"ref": "main"}, "head": {"sha": head}}

    @staticmethod
    def status(context, state, t, creator=BOT, url_run=None):
        return {"id": t, "context": context, "state": state, "created_at": ts(t), "creator": {"login": creator},
                "target_url": f"https://github.com/{REPO}/actions/runs/{url_run}" if url_run else ""}

    def _hit(self, path):
        self.api_calls += 1
        for marker in self.fail:
            if marker in path:
                raise github_api.ApiError("synthetic")

    def get_optional(self, path, params=None):
        self._hit(path)
        prefix = f"/repos/{REPO}"
        if path.startswith(prefix + "/git/ref/tags/"):
            obj = self.tags.get(path.rsplit("/", 1)[1])
            return None if obj is None else {"object": dict(obj)}
        if path.startswith(prefix + "/contents/"):
            text = self.files.get((path[len(prefix + "/contents/"):], params["ref"]))
            return None if text is None else b64(text)
        raise AssertionError(path)

    def get(self, path, params=None):
        prefix = f"/repos/{REPO}"
        if path == prefix + "/git/ref/heads/main":
            self._hit(path)
            return {"object": {"sha": self.head}}
        if path.startswith(prefix + "/git/tags/"):
            self._hit(path)
            return {"object": dict(self.annotated[path.rsplit("/", 1)[1]])}
        if path.startswith(prefix + "/contents/"):
            data = self.get_optional(path, params)
            if data is None:
                raise github_api.ApiError("404")
            return data
        if path.startswith(prefix + "/actions/runs/"):
            self._hit(path)
            run = self.runs.get(int(path.rsplit("/", 1)[1]))
            if run is None:
                raise github_api.ApiError("404")
            return copy.deepcopy(run)
        if path.startswith(prefix + "/commits/"):
            self._hit(path)
            commit = path.rsplit("/", 1)[1]
            return {"sha": commit, "parents": [{"sha": p} for p in self.parents[commit]]}
        raise AssertionError(path)

    def get_all(self, path, params=None, key=None):
        self._hit(path)
        prefix = f"/repos/{REPO}"
        if path == prefix + "/tags":
            out = []
            for name, obj in self.tags.items():
                commit = obj["sha"] if obj["type"] == "commit" else self.annotated[obj["sha"]]["sha"]
                out.append({"name": name, "commit": {"sha": commit}})
            return out
        if path.endswith("/check-runs"):
            return copy.deepcopy(self.check_runs.get(path.split("/")[-2], []))
        if path.endswith("/pulls"):
            return copy.deepcopy(self.pulls.get(path.split("/")[-2], []))
        if path.endswith("/statuses"):
            return copy.deepcopy(list(reversed(self.statuses.get(path.split("/")[-2], []))))
        if path.endswith("/release-gate.yml/runs"):
            return copy.deepcopy(self.tag_runs.get(params["branch"], []))
        raise AssertionError(path)

    def create_status(self, sha_, state, context, description, target_url):
        self.writes.append((sha_, state, context, description, target_url))


def dispatch_env(tag="v0.3.0", sha_=C3, workflow_sha=None, ref="refs/heads/main", workflow="release-gate.yml"):
    return {
        "GITHUB_REPOSITORY": REPO, "GITHUB_SERVER_URL": "https://github.com", "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": ref, "GITHUB_WORKFLOW_REF": f"{REPO}/.github/workflows/{workflow}@refs/heads/main",
        "GITHUB_WORKFLOW_SHA": workflow_sha or sha_, "GITHUB_RUN_ID": "500", "GATE_TAG": tag, "GATE_SHA": sha_,
    }


def push_env(tag="v0.3.0"):
    return {
        "GITHUB_REPOSITORY": REPO, "GITHUB_SERVER_URL": "https://github.com", "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": f"refs/tags/{tag}", "GITHUB_WORKFLOW_REF": f"{REPO}/.github/workflows/release-gate.yml@refs/tags/{tag}",
        "GITHUB_RUN_ID": "600",
    }


def audit_env():
    return {
        "GITHUB_REPOSITORY": REPO, "GITHUB_SERVER_URL": "https://github.com", "GITHUB_EVENT_NAME": "schedule",
        "GITHUB_REF": "refs/heads/main", "GITHUB_WORKFLOW_REF": f"{REPO}/.github/workflows/release-audit.yml@refs/heads/main",
    }


class Base(unittest.TestCase):
    def setUp(self):
        self.repo = FakeRepo()

    def run_mode(self, mode, env_):
        captured = []
        original = rel._finish

        def finish(report, env):
            captured.append(report)
            return original(report, env)

        rel._finish = finish
        try:
            code = rel.run(mode, env_, lambda: self.repo)
        finally:
            rel._finish = original
        return code, captured[0]

    def messages(self, report, level):
        return [m for lvl, m in report.lines if lvl == level]

    def tag_v030(self, annotated=False):
        if annotated:
            self.repo.annotated[sha(0x900)] = {"type": "commit", "sha": C3}
            self.repo.tags["v0.3.0"] = {"type": "tag", "sha": sha(0x900)}
        else:
            self.repo.tags["v0.3.0"] = {"type": "commit", "sha": C3}


class PreflightTests(Base):
    def test_u1_all_conditions_pass(self):
        code, report = self.run_mode("gate", dispatch_env())
        self.assertEqual(code, 0, report.lines)
        self.assertTrue(any(m.startswith("P5") for m in self.messages(report, "PASS")))

    def test_u5_pre_gate_prs_are_informational(self):
        _, report = self.run_mode("gate", dispatch_env())
        info = self.messages(report, "INFO")
        self.assertTrue(any("PR #2" in m and "pre-gate" in m for m in info))
        self.assertTrue(any("PR #4" in m and "pre-gate" in m for m in info))
        self.assertTrue(any("PR #5 review-gate success" in m for m in self.messages(report, "PASS")))

    def test_u2_sha_on_main_but_not_head_fails(self):
        code, report = self.run_mode("gate", dispatch_env(sha_=C2, workflow_sha=C3))
        self.assertEqual(code, 1)
        self.assertTrue(any(m.startswith("P1") for m in self.messages(report, "FAIL")))

    def test_u3_required_checks(self):
        mutations = {
            "missing": lambda runs: runs.pop(0),
            "failure": lambda runs: runs[0].update(conclusion="failure"),
            "pending": lambda runs: runs[0].update(status="in_progress", conclusion=None),
            "other app": lambda runs: runs[0].update(app={"slug": "someone"}),
            "older success, newer failure": lambda runs: runs.append(dict(runs[0], id=9999, conclusion="failure")),
        }
        for name, mutate in mutations.items():
            with self.subTest(case=name):
                self.repo = FakeRepo()
                mutate(self.repo.check_runs[C3])
                code, report = self.run_mode("gate", dispatch_env())
                self.assertEqual(code, 1)
                self.assertTrue(any(m.startswith("P2") for m in self.messages(report, "FAIL")))

    def test_u4_post_gate_pr_without_review_success(self):
        cases = {
            "no status": [],
            "failure": [FakeRepo.status("review-gate", "failure", 50)],
            "forged creator": [FakeRepo.status("review-gate", "success", 50, creator=OWNER)],
            "success then withdrawn": [FakeRepo.status("review-gate", "success", 50), FakeRepo.status("review-gate", "failure", 51)],
        }
        for name, statuses in cases.items():
            with self.subTest(case=name):
                self.repo = FakeRepo()
                self.repo.statuses[H5] = statuses
                code, report = self.run_mode("gate", dispatch_env())
                self.assertEqual(code, 1)
                self.assertTrue(any(m.startswith("P3 PR #5") for m in self.messages(report, "FAIL")))

    def test_u4b_commit_without_merged_pr_fails(self):
        self.repo.pulls[C3] = []
        code, report = self.run_mode("gate", dispatch_env())
        self.assertEqual(code, 1)

    def test_u6_version_and_changelog(self):
        for path, text in (
            ("linux_health_reporter/__init__.py", '__version__ = "0.3.1"\n'),
            ("CHANGELOG.md", "## [0.3.0] — unreleased\n"),
            ("CHANGELOG.md", "## [0.3.0]\n"),
        ):
            with self.subTest(path=path, text=text):
                self.repo = FakeRepo()
                self.repo.files[(path, C3)] = text
                code, report = self.run_mode("gate", dispatch_env())
                self.assertEqual(code, 1)
                self.assertTrue(any(m.startswith("P4") for m in self.messages(report, "FAIL")))

    def test_u7_existing_tag_fails(self):
        self.tag_v030()
        code, report = self.run_mode("gate", dispatch_env())
        self.assertEqual(code, 1)
        self.assertTrue(any(m.startswith("P5") for m in self.messages(report, "FAIL")))

    def test_u11_invalid_inputs_fail_without_api_calls(self):
        def no_client():
            raise AssertionError("API must not be used with invalid inputs")
        for tag, sha_ in (("v0.3", C3), ("0.3.0", C3), ("v0.3.0;rm -rf", C3), ("v01.3.0", C3), ("v0.3.0", C3[:39]),
                          ("v0.3.0", "AB" * 20), ("v0.3.0", "g" * 40), (None, C3), ("v0.3.0", None)):
            with self.subTest(tag=tag, sha=sha_):
                e = dispatch_env()
                e["GATE_TAG"], e["GATE_SHA"] = tag, sha_
                self.assertEqual(rel.run("gate", e, no_client), 1)
                self.assertEqual(rel.run("record", e, no_client), 1)
        e = push_env()
        e["GITHUB_REF"] = "refs/heads/v0.3.0"
        self.assertEqual(rel.run("gate", e, no_client), 1)

    def test_u12_provenance(self):
        for e in (
            dispatch_env(ref="refs/heads/feature"),
            dispatch_env(workflow="other.yml"),
            dispatch_env(workflow_sha=C2),
        ):
            with self.subTest(e=(e["GITHUB_REF"], e["GITHUB_WORKFLOW_REF"], e["GITHUB_WORKFLOW_SHA"])):
                self.repo = FakeRepo()
                code, report = self.run_mode("gate", e)
                self.assertEqual(code, 1)
                self.assertTrue(any(m.startswith("provenance") for m in self.messages(report, "FAIL")))
                self.assertFalse(any(m.startswith("P1") for m in self.messages(report, "PASS")))

    def test_api_error_fails_closed(self):
        self.repo.fail.add("/check-runs")
        code, report = self.run_mode("gate", dispatch_env())
        self.assertEqual(code, 1)


class RecordTests(Base):
    def test_record_writes_evidence(self):
        code, _ = self.run_mode("record", dispatch_env())
        self.assertEqual(code, 0)
        self.assertEqual(self.repo.writes, [(C3, "success", "release-preflight/v0.3.0", f"preflight PASS for v0.3.0 at {C3[:7]}",
                                             f"https://github.com/{REPO}/actions/runs/500")])

    def test_record_refuses_when_main_moved_or_tag_exists(self):
        self.repo.head = C4
        code, _ = self.run_mode("record", dispatch_env(workflow_sha=C4))
        self.assertEqual((code, self.repo.writes), (1, []))
        self.repo = FakeRepo()
        self.tag_v030()
        code, _ = self.run_mode("record", dispatch_env())
        self.assertEqual((code, self.repo.writes), (1, []))

    def test_record_is_not_applicable_to_tag_pushes(self):
        self.tag_v030()
        code, report = self.run_mode("record", push_env())
        self.assertEqual((code, self.repo.writes), (0, []))
        self.assertTrue(self.messages(report, "INFO"))


class PostTagTests(Base):
    def setUp(self):
        super().setUp()
        self.tag_v030()

    def test_post_tag_pass(self):
        code, report = self.run_mode("gate", push_env())
        self.assertEqual(code, 0, report.lines)

    def test_u8_missing_tag(self):
        del self.repo.tags["v0.3.0"]
        code, report = self.run_mode("gate", push_env())
        self.assertEqual(code, 1)
        self.assertTrue(any(m.startswith("T1") for m in self.messages(report, "FAIL")))

    def test_u9_main_moved_after_tag_still_passes(self):
        self.repo.head = C4
        code, report = self.run_mode("gate", push_env())
        self.assertEqual(code, 0, report.lines)

    def test_u10_commit_off_main_fails(self):
        self.repo.tags["v0.3.0"] = {"type": "commit", "sha": OFF}
        code, report = self.run_mode("gate", push_env())
        self.assertEqual(code, 1)
        self.assertTrue(any(m.startswith("T2") for m in self.messages(report, "FAIL")))

    def test_u14_annotated_tag(self):
        self.tag_v030(annotated=True)
        code, report = self.run_mode("gate", push_env())
        self.assertEqual(code, 0, report.lines)

    def test_u15_missing_preflight_is_fail_not_warning(self):
        self.repo.statuses[C3] = []
        code, report = self.run_mode("gate", push_env())
        self.assertEqual(code, 1)
        self.assertTrue(any(m.startswith("T4 no preflight") for m in self.messages(report, "FAIL")))

    def test_u16_preflight_for_other_tag_or_commit(self):
        self.repo.statuses[C3] = [FakeRepo.status("release-preflight/v0.3.1", "success", 100, url_run=500)]
        self.assertEqual(self.run_mode("gate", push_env())[0], 1)
        self.repo = FakeRepo()
        self.tag_v030()
        self.repo.statuses[C2] = self.repo.statuses.pop(C3)
        self.assertEqual(self.run_mode("gate", push_env())[0], 1)

    def test_u17_forged_status_by_user_token(self):
        self.repo.statuses[C3] = [FakeRepo.status("release-preflight/v0.3.0", "success", 100, creator=OWNER, url_run=500)]
        code, report = self.run_mode("gate", push_env())
        self.assertEqual(code, 1)
        self.assertTrue(any("creator" in m for m in self.messages(report, "FAIL")))

    def test_u18_run_criteria(self):
        changes = {
            "path": ".github/workflows/other.yml", "event": "push", "head_branch": "feature", "head_sha": C2,
            "conclusion": "failure", "display_title": "release-preflight v0.3.1 " + C3,
        }
        for key, value in changes.items():
            with self.subTest(key=key):
                self.repo = FakeRepo()
                self.tag_v030()
                self.repo.runs[500][key] = value
                code, report = self.run_mode("gate", push_env())
                self.assertEqual(code, 1)
                self.assertTrue(any(m.startswith("T4 preflight evidence") for m in self.messages(report, "FAIL")))
        self.repo = FakeRepo()
        self.tag_v030()
        self.repo.runs[500]["path"] = ".github/workflows/release-gate.yml@refs/heads/main"
        self.assertEqual(self.run_mode("gate", push_env())[0], 0)
        for url in ("https://evil.example/actions/runs/500", f"https://github.com/{REPO}/actions/runs/500/x", ""):
            with self.subTest(url=url):
                self.repo = FakeRepo()
                self.tag_v030()
                self.repo.statuses[C3][0]["target_url"] = url
                self.assertEqual(self.run_mode("gate", push_env())[0], 1)

    def test_u19_preflight_created_after_tag(self):
        self.repo.statuses[C3] = [FakeRepo.status("release-preflight/v0.3.0", "success", 300, url_run=500)]
        code, report = self.run_mode("gate", push_env())
        self.assertEqual(code, 1)
        self.assertTrue(any("created after the tag" in m for m in self.messages(report, "FAIL")))


class AuditTests(Base):
    def test_u13_pre_gate_tags_are_informational(self):
        code, report = self.run_mode("audit", audit_env())
        self.assertEqual(code, 0, report.lines)
        self.assertEqual(len([m for m in self.messages(report, "INFO") if "pre-gate" in m and m.startswith("v0.")]), 2)

    def test_audit_valid_and_invalid_tags(self):
        self.tag_v030()
        self.assertEqual(self.run_mode("audit", audit_env())[0], 0)
        self.repo.tag_runs["v0.3.0"] = []
        code, report = self.run_mode("audit", audit_env())
        self.assertEqual(code, 1)
        self.assertTrue(any("no post-tag gate run" in m for m in self.messages(report, "FAIL")))

    def test_audit_detects_tag_off_main(self):
        self.repo.tags["v0.3.0"] = {"type": "commit", "sha": OFF}
        code, report = self.run_mode("audit", audit_env())
        self.assertEqual(code, 1)

    def test_audit_provenance(self):
        e = audit_env()
        e["GITHUB_WORKFLOW_REF"] = f"{REPO}/.github/workflows/release-audit.yml@refs/heads/feature"
        self.assertEqual(self.run_mode("audit", e)[0], 1)
        e = audit_env()
        e["GITHUB_EVENT_NAME"], e["GITHUB_REF"] = "workflow_dispatch", "refs/heads/feature"
        self.assertEqual(self.run_mode("audit", e)[0], 1)

    def test_unsupported_modes(self):
        e = audit_env()
        e["GITHUB_EVENT_NAME"] = "push"
        self.assertEqual(rel.run("audit", e, lambda: self.repo), 1)


class StaticTests(unittest.TestCase):
    def test_wf8_inputs_validated_before_any_client(self):
        source = inspect.getsource(rel.run)
        self.assertLess(source.index("valid_tag(tag)"), source.index("client_factory()"))
        self.assertLess(source.index("valid_sha(sha)"), source.index("client_factory()"))

    def test_only_preflight_context_is_written(self):
        module = inspect.getsource(rel)
        writes = [line.strip() for line in module.splitlines() if "create_status(" in line]
        self.assertEqual(len(writes), 1)
        self.assertIn("PREFLIGHT_CONTEXT.format(tag=tag)", writes[0])


if __name__ == "__main__":
    unittest.main()
