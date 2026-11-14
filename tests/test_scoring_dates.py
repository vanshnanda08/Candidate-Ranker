"""Offline regressions for one scoring date and unified honeypot explanations."""
import copy
import csv
from datetime import date, timedelta
import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import rank
import server
from pipeline import behavioral, encoder, honeypot, ranking
from pipeline.dates import parse_as_of
from test_embedding_cache import FakeEncoder

AS_OF = date(2026, 11, 13)


def clean_candidate():
    return {'profile': {'years_of_experience': 0}, 'redrob_signals': {},
            'career_history': [], 'education': [], 'skills': []}


class ActivityDateTests(unittest.TestCase):
    def score(self, value):
        return behavioral.score_behavioral({'redrob_signals': {'last_active_date': value}}, as_of=AS_OF)

    def test_same_day_is_zero_not_fallback(self):
        result = self.score(AS_OF.isoformat())
        self.assertEqual(result['inactive_days'], 0)
        self.assertEqual(result['activity_score'], 1.0)

    def test_missing_malformed_and_future_dates_use_fallback(self):
        for value in (None, '', 'not a date', '2026-02-29', '2026-1-01', 42, ['bad'],
                      '2026-11-14', '2099-01-01', '2026-11-13T12:00:00'):
            with self.subTest(value=value):
                result = self.score(value)
                self.assertEqual(result['inactive_days'], 365)
                self.assertEqual(result['activity_score'], .1)
        self.assertEqual(behavioral.score_behavioral({'redrob_signals': {}}, AS_OF)['inactive_days'], 365)

    def test_activity_thresholds_and_weight_are_unchanged(self):
        for days, expected in [(0, 1), (1, 1), (7, 1), (8, .9), (30, .9),
                               (31, .7), (90, .7), (91, .4), (180, .4), (181, .1), (365, .1)]:
            with self.subTest(days=days):
                result = self.score((AS_OF - timedelta(days=days)).isoformat())
                self.assertEqual(result['inactive_days'], days)
                self.assertEqual(result['activity_score'], expected)
        high = self.score((AS_OF - timedelta(days=7)).isoformat())
        low = self.score((AS_OF - timedelta(days=8)).isoformat())
        self.assertAlmostEqual(high['behavioral_score'] - low['behavioral_score'], .02)

    def test_leap_day_and_compatibility_default(self):
        self.assertEqual(behavioral.parse_date('2024-02-29'), date(2024, 2, 29))
        with patch.object(behavioral, 'date') as clock:
            clock.today.return_value = AS_OF
            self.assertEqual(behavioral.score_behavioral({'redrob_signals': {'last_active_date': '2026-11-13'}})['inactive_days'], 0)
            clock.today.assert_called_once()


class HoneypotDateTests(unittest.TestCase):
    def assert_evaluation(self, candidate, expected, codes, as_of=AS_OF):
        penalty, flags = honeypot.evaluate_honeypot(candidate, as_of=as_of)
        self.assertAlmostEqual(penalty, expected)
        self.assertEqual(flags, [honeypot.RULE_MESSAGES[code] for code in codes])
        self.assertTrue(all(isinstance(flag, str) for flag in flags))
        self.assertEqual(honeypot.honeypot_penalty(candidate, as_of), penalty)
        self.assertEqual(honeypot.honeypot_flags(candidate, as_of), flags)
        self.assertEqual(honeypot.is_honeypot(candidate, as_of=as_of), penalty < .2)

    def test_every_rule_has_matching_penalty_and_explanation(self):
        cases = []
        c = clean_candidate(); c['profile']['years_of_experience'] = 4; c['education'] = [{'end_year': 2025}]
        cases.append((c, .05, 'impossible_experience'))
        c = clean_candidate(); c['skills'] = [{'name': 'Advanced Python', 'proficiency': 'expert'}]
        c['redrob_signals']['skill_assessment_scores'] = {'Python': 24}
        cases.append((c, .7, 'assessment_proficiency_mismatch_mild'))
        c = copy.deepcopy(c); c['skills'].append({'name': 'SQL', 'proficiency': 'expert'})
        c['redrob_signals']['skill_assessment_scores']['SQL'] = 24
        cases.append((c, .3, 'assessment_proficiency_mismatch'))
        c = clean_candidate(); c['redrob_signals']['profile_completeness_score'] = 91
        cases.append((c, .4, 'unverified_complete_profile'))
        c = clean_candidate(); c['career_history'] = [{'start_date': '2025-01-01', 'end_date': '2026-12-01'} for _ in range(4)]
        cases.append((c, .3, 'multiple_overlapping_jobs'))
        c = clean_candidate(); c['redrob_signals'].update(endorsements_received=501, connection_count=9)
        cases.append((c, .3, 'endorsement_connection_mismatch'))
        c = clean_candidate(); c['career_history'] = [{'start_date': '2026-11-14'}]
        cases.append((c, .1, 'future_start_date'))
        c = clean_candidate(); c['education'] = [{'end_year': 2028}]
        cases.append((c, .2, 'future_graduation'))
        c = clean_candidate(); c['education'] = [{'start_year': 2021, 'end_year': 2020}]
        cases.append((c, .2, 'inverted_education_dates'))
        for candidate, multiplier, code in cases:
            with self.subTest(rule=code):
                self.assert_evaluation(candidate, multiplier, [code])

    def test_ongoing_jobs_end_at_as_of(self):
        c = clean_candidate()
        c['career_history'] = [{'start_date': f'{year}-01-01', 'end_date': None}
                               for year in (2019, 2020, 2021, 2022)]
        self.assert_evaluation(c, 1, [], date(2022, 1, 1))
        self.assert_evaluation(c, .3, ['multiple_overlapping_jobs'], date(2022, 12, 31))

    def test_future_job_and_year_checks_follow_explicit_date(self):
        c = clean_candidate(); c['career_history'] = [{'start_date': '2026-11-13'}]
        self.assert_evaluation(c, 1, [], AS_OF)
        self.assert_evaluation(c, .1, ['future_start_date'], AS_OF - timedelta(days=1))
        c = clean_candidate(); c['education'] = [{'end_year': 2027}]
        self.assert_evaluation(c, 1, [], AS_OF)
        c['education'][0]['end_year'] = 2028
        self.assert_evaluation(c, .2, ['future_graduation'], AS_OF)
        self.assert_evaluation(c, 1, [], date(2027, 1, 1))
        c = clean_candidate(); c['profile']['years_of_experience'] = 3; c['education'] = [{'end_year': 2026}]
        self.assert_evaluation(c, .05, ['impossible_experience'], AS_OF)
        self.assert_evaluation(c, 1, [], date(2027, 1, 1))

    def test_multiplier_product_floor_and_rule_boundaries(self):
        c = clean_candidate(); c['profile']['years_of_experience'] = 4
        c['education'] = [{'end_year': 2025}]; c['career_history'] = [{'start_date': '2026-11-14'}]
        self.assert_evaluation(c, .01, ['impossible_experience', 'future_start_date'])
        c = clean_candidate(); c['redrob_signals'].update(profile_completeness_score=91, linkedin_connected=True)
        self.assert_evaluation(c, 1, [])  # LinkedIn verification prevents this penalty and flag.
        c['redrob_signals'].update(linkedin_connected=False, profile_completeness_score=90,
                                   endorsements_received=500, connection_count=9)
        self.assert_evaluation(c, 1, [])
        c['redrob_signals'].update(endorsements_received=501, connection_count=10)
        self.assert_evaluation(c, 1, [])
        c['skills'] = [{'name': 'Python', 'proficiency': 'expert'}]
        c['redrob_signals']['skill_assessment_scores'] = {'Python': 25}
        self.assert_evaluation(c, 1, [])

    def test_missing_malformed_career_dates_and_compatibility_calls(self):
        c = clean_candidate(); c['career_history'] = [{'start_date': 'bad', 'end_date': None}]
        with patch.object(honeypot, 'date') as clock:
            clock.today.return_value = AS_OF
            self.assertEqual(honeypot.honeypot_penalty(c), 1)
            self.assertEqual(honeypot.honeypot_flags(c), [])
            self.assertFalse(honeypot.is_honeypot(c, .5))


class DateBoundaryTests(unittest.TestCase):
    def test_strict_dates_at_cli_and_http_boundaries(self):
        invalid = ['2026-02-29', '2024-02-30', '2026-13-01', '0000-01-01',
                   '2026-1-01', '26-11-13', '20261113', '2026-11-13T00:00:00',
                   ' 2026-11-13', '2026-11-13\n', '２０２６-１１-１３', '']
        client = TestClient(server.app)
        with patch.object(server, 'get_candidates', side_effect=AssertionError('dataset read')):
            for value in invalid:
                with self.subTest(value=value), redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        rank.parse_args(['--candidates', 'unused', '--as-of', value])
                    self.assertEqual(error.exception.code, 2)
                    self.assertEqual(client.post('/api/rank', json={'as_of': value}).status_code, 422)
            for value in (20261113, 0, True, [], {}):
                self.assertEqual(client.post('/api/rank', json={'as_of': value}).status_code, 422)
        for value in ('2024-02-29', '2026-11-13'):
            self.assertEqual(rank.parse_args(['--candidates', 'unused', '--as-of', value]).as_of, parse_as_of(value))
            self.assertEqual(server.RankRequest(as_of=value).as_of, parse_as_of(value))
        self.assertIsNone(server.RankRequest().as_of)
        self.assertIsNone(server.RankRequest(as_of=None).as_of)
        self.assertIsNone(rank.parse_args(['--candidates', 'unused']).as_of)

    def test_run_resolves_local_date_once_and_passes_it_to_each_evaluation(self):
        sample = json.loads((Path(__file__).resolve().parents[1] / 'sample_candidates.json').read_text())[:2]
        with tempfile.TemporaryDirectory() as tmp, patch.object(encoder, 'CACHE_DIR', Path(tmp)), \
             patch.object(ranking, 'date') as clock, \
             patch.object(behavioral, 'date') as behavioral_clock, \
             patch.object(honeypot, 'date') as honeypot_clock, \
             patch.object(ranking, 'score_behavioral', wraps=behavioral.score_behavioral) as behavior, \
             patch.object(ranking, 'evaluate_honeypot', wraps=honeypot.evaluate_honeypot) as hp:
            clock.today.return_value = AS_OF
            behavioral_clock.today.side_effect = AssertionError('second clock read')
            honeypot_clock.today.side_effect = AssertionError('second clock read')
            result = ranking.rank_candidates(sample, model_factory=FakeEncoder)
            clock.today.assert_called_once()
            self.assertEqual(behavior.call_count, 2)
            self.assertEqual(hp.call_count, 2)
            self.assertTrue(all(call.kwargs['as_of'] == AS_OF for call in behavior.call_args_list + hp.call_args_list))
            self.assertTrue(all(isinstance(row['honeypot_flags'], list) for row in result))
            clock.today.reset_mock()
            ranking.rank_candidates(sample, model_factory=FakeEncoder, as_of=AS_OF)
            clock.today.assert_not_called()

    def test_explicit_date_cli_api_parity_and_no_flag_recalculation(self):
        sample = json.loads((Path(__file__).resolve().parents[1] / 'sample_candidates.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sample.json'; path.write_text(json.dumps(sample))
            output = Path(tmp) / 'sample.csv'
            with patch.object(encoder, 'CACHE_DIR', Path(tmp) / 'cache'), \
                 patch.object(ranking, 'load_model', side_effect=FakeEncoder), \
                 patch.object(server, 'get_model', side_effect=FakeEncoder), \
                 patch.object(ranking, 'evaluate_honeypot', wraps=honeypot.evaluate_honeypot) as evaluated, \
                 patch.object(honeypot, 'honeypot_flags', side_effect=AssertionError('recalculated flags')), \
                 redirect_stdout(io.StringIO()):
                rank.main(['--candidates', str(path), '--sample', '--top-n', '20', '--no-llm',
                           '--as-of', AS_OF.isoformat(), '--out', str(output)])
                self.assertEqual(evaluated.call_count, 50)
                evaluated.reset_mock()
                response = TestClient(server.app).post('/api/rank', json={'data_path': str(path), 'top_n': 20,
                              'use_llm': False, 'as_of': AS_OF.isoformat()})
                self.assertEqual(evaluated.call_count, 50)
            self.assertEqual(response.status_code, 200, response.text)
            with output.open() as handle: cli = list(csv.DictReader(handle))
            api = response.json()['results']
            self.assertEqual([(r['candidate_id'], int(r['rank']), float(r['score'])) for r in cli],
                             [(r['candidate_id'], r['rank'], r['display_score']) for r in api])
            by_id = {c['candidate_id']: c for c in sample}
            for row in api:
                penalty, flags = honeypot.evaluate_honeypot(by_id[row['candidate_id']], AS_OF)
                self.assertEqual(row['honeypot_penalty'], round(penalty, 4))
                self.assertEqual(row['honeypot_flags'], flags)
                self.assertTrue(all(isinstance(flag, str) for flag in flags))


if __name__ == '__main__':
    unittest.main()
