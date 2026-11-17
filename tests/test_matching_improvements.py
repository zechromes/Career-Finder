# Regression coverage for matching improvements; fixtures and assertions document the expected behavior.
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock
from backend.search.ranking import bm25_rank, reciprocal_rank_fusion, retrieval_queries
from backend.schemas.evaluation import RequirementVerdict
from backend.evaluation.evidence import score_requirements
from backend.search.embedding_cache import CachedJobEmbeddings
from backend.search.collection import deduplicate_jobs
from scripts.measure_matching import measure


class MatchingTests(unittest.TestCase):
    def test_multi_query_keeps_roles_skills_and_recent_experience_separate(self):
        queries = retrieval_queries(
            {
                "name": "Private",
                "tech_skills": ["C++", "Python"],
                "work_history": ["Build APIs 2024-Present"],
            },
            ["Developer", "Analyst"],
        )
        # Check the expected behavior: multi query keeps roles skills and recent experience separate.
        self.assertEqual(queries[:2], ["Developer", "Analyst"])
        self.assertIn("C++, Python", queries)
        self.assertIn("Build APIs", queries[-1])
        self.assertNotIn("Private", " ".join(queries))

    def test_each_resume_entry_is_its_own_query_within_the_experience_vote(self):
        from backend.search.ranking import retrieval_query_weights

        profile = {
            "tech_skills": ["Python"],
            "work_history": ["Build Python APIs 2024-Present"],
            "sections": [{"heading": "Projects", "entries": ["dbt job tracker"]}],
            "education": ["Bachelor of Computing 2015"],
        }
        weights = retrieval_query_weights(profile, ["Developer"])
        # Votes are shares of 1: roles 0.5, skills 1 and experience 1 of 2.5 in total.
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertAlmostEqual(weights["Developer"], 0.2)
        self.assertAlmostEqual(weights["Python"], 0.4)
        # Entries split the experience share, recent and relevant work first.
        entries = ["Build Python APIs 2024-Present", "dbt job tracker", "Bachelor of Computing 2015"]
        self.assertAlmostEqual(sum(weights[entry] for entry in entries), 0.4)
        self.assertGreater(weights[entries[0]], weights[entries[1]])
        self.assertGreater(weights[entries[1]], weights[entries[2]])

    def test_skill_groups_are_weighted_by_evidence_not_by_listing(self):
        from backend.search.ranking import retrieval_query_weights

        sentence = "Experience building APIs with Python and FastAPI."
        profile = {
            "tech_skills": ["Python", "FastAPI", "Excel", "Unity", "Laravel"],
            "skill_groups": [
                {"name": "Backend", "skills": ["fastapi", "Python"], "query": sentence},
                {"name": "Data", "skills": ["Excel"]},
                {"name": "Other", "skills": ["Unity", "Laravel", "Python"]},
            ],
            "work_history": [
                "Engineer | Built FastAPI services in Python | 2025 - Present",
                "Analyst | Excel reporting | 2016 - 2017",
            ],
        }
        weights = retrieval_query_weights(profile, ["Backend Developer"])
        # Proven groups use their requirement sentence; old evidence gets a smaller share.
        # Backend averages two skills at 0.5 + 1.0 (current); Excel is 0.5 + 0.3 (2016).
        self.assertAlmostEqual(weights[sentence] / weights["Data: Excel"], 1.5 / 0.8)
        # Listed-only skills are dropped, so Unity and Laravel pull in no game or PHP jobs.
        self.assertFalse(any("Unity" in query or "Laravel" in query for query in weights))
        # A skill the extraction found in an entry counts even when the entry never names it.
        profile["tech_skills"] += ["LLMs", "Docker"]
        self.assertNotIn("Other skills: LLMs", retrieval_query_weights(profile, []))
        entry = "Built a resume matcher with GPT 2025 - Present"
        profile["work_history"].append(entry)
        profile["entry_evidence"] = [
            {"entry": entry, "summary": "Built a resume matcher.", "hard_skills": ["LLMs"]}
        ]
        after = retrieval_query_weights(profile, [])
        self.assertIn("Other skills: LLMs", after)
        self.assertIn("Built a resume matcher. Using LLMs.", after)
        self.assertNotIn(entry, after)
        self.assertFalse(any("Docker" in query for query in after))

    def test_keyword_queries_weigh_like_an_average_named_skill(self):
        from backend.search.ranking import retrieval_query_weights

        profile = {
            "tech_skills": ["Python", "FastAPI", "Unity"],
            "work_history": ["Engineer | Built FastAPI services in Python | 2025 - Present"],
            "keyword_queries": ["Python FastAPI Docker", "Unity Kubernetes"],
        }
        weights = retrieval_query_weights(profile, [])
        # Python and FastAPI each score 0.5 + 1.0; the group and the line both average them.
        self.assertAlmostEqual(weights["Python, FastAPI"], weights["Python FastAPI Docker"])
        # Unity is listed only, so a line naming no kept skill is not searched.
        self.assertNotIn("Unity Kubernetes", weights)

    def test_entry_type_and_extracted_end_date_scale_experience(self):
        from backend.search.ranking import retrieval_query_weights

        job, hackathon, undated = "Built Python APIs", "Python hackathon bot", "Python CLI tool"
        profile = {
            "tech_skills": ["Python"],
            "work_history": [job],
            "sections": [{"heading": "Projects", "entries": [hackathon, undated]}],
            "entry_evidence": [
                {"entry": job, "type": "job", "end": "present"},
                {"entry": hackathon, "type": "hackathon", "end": "present"},
            ],
        }
        weights = retrieval_query_weights(profile, [])
        # Current job 1.0, current hackathon 0.6 (type), undated project 0.6 (recency),
        # within the experience half of the total (skills hold the other half).
        self.assertAlmostEqual(weights[job], 0.5 * 1.0 / 2.2)
        self.assertAlmostEqual(weights[hackathon], 0.5 * 0.6 / 2.2)
        self.assertAlmostEqual(weights[undated], 0.5 * 0.6 / 2.2)

    def test_legacy_builder_stays_available_for_comparison(self):
        from unittest.mock import patch
        from backend.search.ranking import retrieval_queries, retrieval_query_weights

        profile = {"tech_skills": ["Python", "SQL"], "work_history": ["Built APIs 2024-Present"]}
        legacy = retrieval_queries(profile, ["Developer"], builder="legacy")
        self.assertEqual(legacy, ["Developer", "Python SQL", "Built APIs 2024-Present"])
        with patch.dict("os.environ", {"QUERY_BUILDER": "legacy"}):
            self.assertEqual(retrieval_queries(profile, ["Developer"]), legacy)
            self.assertEqual(retrieval_query_weights(profile, ["Developer"])["Python SQL"], 1.0)
        self.assertNotIn("Python SQL", retrieval_queries(profile, ["Developer"]))

    def test_skills_builder_searches_skills_weighted_by_experience(self):
        from unittest.mock import patch
        from backend.search.ranking import retrieval_query_weights

        entry = "Built employee-record prototypes in Vue and Node.js 2025-Present"
        profile = {
            "tech_skills": ["Vue", "Node.js", "Excel"],
            "skill_groups": [
                {"name": "Web", "skills": ["Vue", "Node.js"]},
                {"name": "Data", "skills": ["Excel"]},
            ],
            "work_history": [entry, "Analyst | Excel reporting | 2016 - 2017"],
            "entry_evidence": [
                {"entry": entry, "summary": "Built employee-record prototypes.", "hard_skills": ["Vue", "Node.js"]}
            ],
        }
        weights = retrieval_query_weights(profile, ["Frontend Developer"], builder="skills")
        # Entry text is never a query, so its domain words cannot pull in HR postings.
        self.assertEqual(set(weights), {"Frontend Developer", "Web: Vue, Node.js", "Data: Excel"})
        # Recent use still makes Web outweigh Excel: an average of 0.5 + 1.0 against 0.5 + 0.3.
        self.assertAlmostEqual(weights["Web: Vue, Node.js"] / weights["Data: Excel"], 1.5 / 0.8)
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        with patch.dict("os.environ", {"QUERY_BUILDER": "skills"}):
            self.assertEqual(retrieval_query_weights(profile, ["Frontend Developer"]), weights)
        # A skill only an entry shows stays searchable once its entry text is not a query.
        # It joins the group its entry already uses; one no group shares goes to "Other skills".
        profile["entry_evidence"][0]["hard_skills"] += ["React", "vue"]
        debug = "Fixed checkout bugs 2025-Present"
        profile["work_history"].append(debug)
        profile["entry_evidence"].append({"entry": debug, "hard_skills": ["Debugging"]})
        shown = retrieval_query_weights(profile, [], builder="skills")
        self.assertIn("Web: Vue, Node.js, React", shown)
        self.assertIn("Other skills: Debugging", shown)
        self.assertFalse(any("vue," in query for query in shown))
        # The evidence builder keeps entry-only skills in its experience queries instead.
        self.assertIn("Web: Vue, Node.js", retrieval_query_weights(profile, []))
        with patch.dict("os.environ", {"QUERY_BUILDER": "skill"}), self.assertRaises(ValueError):
            retrieval_query_weights(profile, [])

    def test_skill_names_match_how_resumes_write_skills(self):
        from backend.search.ranking import _mentions, skill_label, tokens

        # Each skill as resumes list it, an entry that shows it, and one that must not.
        cases = [
            ("Docker (basics)", "Containerised the API with Docker", "Covered basic SQL"),
            ("containerization basics (Docker)", "Shipped Docker images", "Learned the basics"),
            ("Git/GitHub", "Reviewed pull requests on GitHub", "Wrote digital guides"),
            ("Unix/Linux Command Basics", "Automated Linux servers", "Gave basic commands"),
            ("Claude, GPT and Gemini integration", "Called the Gemini API", "Built an integration"),
            ("Retrieval-augmented generation (RAG)", "Built a RAG chatbot", "Generated reports"),
            ("ExpressJS", "Wrote Express.js routes", "Expressed ideas clearly"),
            ("Shell scripting", "Wrote shell scripts", "Wrote Python scripts"),
            ("RESTful API development", "Developed RESTful APIs", "Developed a mobile app"),
            ("scikit-learn", "Trained scikit-learn models", "Learn new tools quickly"),
        ]
        for skill, shows, unrelated in cases:
            with self.subTest(skill=skill):
                self.assertTrue(_mentions(skill, tokens(shows)))
                self.assertFalse(_mentions(skill, tokens(unrelated)))
        # Level words describe the candidate, so queries leave them out.
        self.assertEqual(skill_label("Docker (basics)"), "Docker")
        self.assertEqual(skill_label("containerization basics (Docker)"), "containerization (Docker)")
        self.assertEqual(skill_label("Python"), "Python")

    def test_skills_builder_keeps_listed_only_skills_at_low_weight(self):
        from backend.search.ranking import retrieval_query_weights

        profile = {
            "tech_skills": ["Python", "Docker (basics)"],
            "skill_groups": [
                {"name": "Backend", "skills": ["Python"]},
                {"name": "DevOps", "skills": ["Docker (basics)"], "query": "Basic Docker experience."},
            ],
            "work_history": ["Built Python APIs 2025-Present"],
        }
        weights = retrieval_query_weights(profile, [], builder="skills")
        # Python: 0.5 listed + 1.0 current job; Docker: listed only, 0.2, under its sentence.
        self.assertAlmostEqual(weights["Backend: Python"], 1.5 / 1.7)
        self.assertAlmostEqual(weights["Basic Docker experience."], 0.2 / 1.7)
        # The evidence builder still drops skills no entry shows.
        self.assertFalse(any("Docker" in query for query in retrieval_query_weights(profile, [])))

    def test_long_skill_list_does_not_outweigh_a_strongly_proven_short_one(self):
        from backend.search.ranking import retrieval_query_weights

        ml = ["PyTorch", "Keras", "NumPy", "Pandas", "OpenCV", "Seaborn"]
        profile = {
            "tech_skills": ["LangChain", "RAG", *ml],
            "skill_groups": [
                {"name": "LLM applications", "skills": ["LangChain", "RAG"]},
                {"name": "Machine learning", "skills": ml},
            ],
            "work_history": ["Built RAG agents with LangChain 2025-Present"],
            "sections": [{"heading": "Projects", "entries": [f"Course notebook using {', '.join(ml)} 2020"]}],
        }
        weights = retrieval_query_weights(profile, [], builder="skills")
        llm, many = "LLM applications: LangChain, RAG", f"Machine learning: {', '.join(ml)}"
        self.assertGreater(weights[llm], weights[many])
        # Listing more equally proven skills does not change a group's share.
        profile["tech_skills"].append("Matplotlib")
        profile["skill_groups"][1]["skills"].append("Matplotlib")
        profile["sections"][0]["entries"][0] = profile["sections"][0]["entries"][0].replace(" 2020", ", Matplotlib 2020")
        longer = retrieval_query_weights(profile, [], builder="skills")
        self.assertAlmostEqual(longer[f"{many}, Matplotlib"], weights[many])

    def test_soft_skills_are_not_searched_unless_given_a_vote(self):
        from unittest.mock import patch
        from backend.search.ranking import retrieval_query_weights

        entry = "Team lead | Mentored two interns | 2025 - Present"
        profile = {
            "tech_skills": ["Python"],
            "soft_skills": ["Communication", "Mentoring"],
            "work_history": [entry],
            "entry_evidence": [{"entry": entry, "soft_skills": ["Mentoring", "Leadership"]}],
        }
        for builder in ("evidence", "skills"):
            weights = retrieval_query_weights(profile, ["Developer"], builder=builder)
            self.assertFalse(any(query.startswith("Soft skills") for query in weights))
            self.assertAlmostEqual(sum(weights.values()), 1.0)
        with patch.dict("os.environ", {"RETRIEVAL_WEIGHTS": '{"votes": {"soft_skills": 0.5}}'}):
            # Only soft skills an entry shows enter the query; listing alone is not enough.
            weights = retrieval_query_weights(profile, ["Developer"])
            self.assertIn("Soft skills: Mentoring, Leadership", weights)
            # An entry edited after extraction falls back to its own words.
            profile["work_history"] = ["Team lead | Coached interns | 2025 - Present"]
            weights = retrieval_query_weights(profile, ["Developer"])
            self.assertIn("Soft skills: Communication, Mentoring", weights)
            self.assertIn("Team lead | Coached interns | 2025 - Present", weights)

    def test_bm25_preserves_exact_tools_and_rrf_has_no_duplicate_votes(self):
        # Check the expected behavior: bm25 preserves exact tools and rrf has no duplicate votes.
        self.assertEqual(
            bm25_rank(["C# backend", "C++ robotics", "Python API"], "C++", 3), [1]
        )
        self.assertEqual(reciprocal_rank_fusion([[0, 0, 1], [1, 2]], 3)[0], 1)

    def row(self, **values):
        fields = dict(
            requirement="Python",
            importance="must_have",
            verdict="met",
            job_quote="Python required",
            resume_quotes=["Built Python APIs"],
        )
        return RequirementVerdict(**(fields | values))

    def test_score_uses_quotes_and_not_model_number(self):
        score, category, _, rows = score_requirements(
            [self.row()], "Built Python APIs", "Python required"
        )
        # Check the expected behavior: score uses quotes and not model number.
        self.assertEqual((score, category), (100, "strong_match"))
        score, category, _, rows = score_requirements(
            [self.row(resume_quotes=["Invented"])], "Built Python APIs", "Python required"
        )
        self.assertEqual(category, "review")
        self.assertEqual(rows[0]["verdict"], "unknown")

    def test_absence_is_not_met_but_cannot_cause_hard_rejection(self):
        result = score_requirements(
            [self.row(verdict="not_met", resume_quotes=[])],
            "Built APIs",
            "Python required",
        )
        # A requirement the resume never mentions is not met, but the job stays for review.
        self.assertEqual(result[1], "review")
        self.assertEqual(result[3][0]["verdict"], "not_met")
        self.assertEqual(score_requirements([], "", "")[:2], (None, "review"))

    def test_quoted_mismatch_rejects_and_invented_quote_does_not(self):
        resume, job = "2 years experience", "Python required"
        shown = score_requirements(
            [self.row(verdict="not_met", resume_quotes=["2 years experience"])],
            resume,
            job,
        )
        self.assertEqual(shown[1], "not_suitable")
        invented = score_requirements(
            [self.row(verdict="not_met", resume_quotes=["No Python at all"])],
            resume,
            job,
        )
        self.assertEqual(invented[1], "review")
        self.assertEqual(invented[3][0]["verdict"], "unknown")

    def test_each_resume_quote_is_checked_and_one_verified_quote_supports(self):
        resume = "Work: Built Python APIs\nProjects: Python job tracker"
        rows = score_requirements(
            [
                self.row(
                    resume_quotes=["Invented Python award", "Python job tracker", "Built Python APIs"]
                )
            ],
            resume,
            "Python required",
        )[3]
        self.assertEqual(rows[0]["verdict"], "met")
        self.assertEqual(rows[0]["resume_quotes_verified"], [False, True, True])
        # Older consumers read the first verified quote.
        self.assertEqual(rows[0]["resume_quote"], "Python job tracker")
        # A saved assessment with one legacy quote is still verified.
        legacy = score_requirements(
            [{**self.row().model_dump(exclude={"resume_quotes"}), "resume_quote": "Built Python APIs"}],
            resume,
            "Python required",
        )[3]
        self.assertTrue(legacy[0]["resume_evidence_verified"])

    def test_every_section_and_the_resume_text_reach_the_assessment_context(self):
        from backend.cli import profile_to_context
        from backend.schemas.resume import ResumeProfile

        context = profile_to_context(
            ResumeProfile(
                sections=[
                    {"heading": "Certifications", "entries": ["AWS Cloud Practitioner | 2025"]},
                    {"heading": "Awards", "entries": []},
                ],
                source_text="Volunteering: Code club mentor",
            )
        )
        self.assertIn("Certifications: AWS Cloud Practitioner | 2025", context)
        self.assertNotIn("Awards:", context)
        self.assertIn("<<<\nVolunteering: Code club mentor\n>>>", context)
        # A quote from the original text verifies, even though extraction missed it.
        self.assertTrue(
            score_requirements(
                [self.row(resume_quotes=["Code club mentor"])], context, "Python required"
            )[3][0]["resume_evidence_verified"]
        )

    def test_older_profiles_turn_projects_into_a_section(self):
        from backend.schemas.resume import ResumeProfile

        profile = ResumeProfile.model_validate(
            {"projects": ["Job tracker | Personal | 2026 | LLM workflow"]}
        )
        self.assertEqual(profile.sections[0].heading, "Projects")
        self.assertEqual(profile.sections[0].entries, ["Job tracker | Personal | 2026 | LLM workflow"])
        self.assertEqual(ResumeProfile.model_validate({}).sections, [])
        self.assertEqual(ResumeProfile.model_validate({}).source_text, "")

    def test_invalid_job_quote_cannot_earn_credit(self):
        # Check the expected behavior: invalid job quote cannot earn credit.
        self.assertEqual(
            score_requirements(
                [self.row()], "Built Python APIs", "No requirements listed"
            )[:2],
            (None, "review"),
        )

    def test_embedding_cache_reuses_content_but_not_candidate_queries(self):
        with TemporaryDirectory() as directory:
            delegate = MagicMock()
            delegate.embed_documents.return_value = [[1.0, 2.0]]
            cache = CachedJobEmbeddings(delegate, directory)
            self.assertEqual(
                cache.embed_documents(["same", "same"]), [[1.0, 2.0], [1.0, 2.0]]
            )
            cache.embed_documents(["same"])
            delegate.embed_documents.assert_called_once_with(["same"])
            cache.embed_query("private candidate")
            delegate.embed_query.assert_called_once_with("private candidate")
            cache.embed_documents(["changed"])
            self.assertEqual(delegate.embed_documents.call_count, 2)

    def test_cross_board_duplicates_require_matching_identity_and_description(self):
        base = dict(
            company="Example",
            title="Engineer",
            location="Sydney",
            description="Build Python APIs and distributed systems. " * 5,
        )
        # Check the expected behavior: cross board duplicates require matching identity and description.
        self.assertEqual(
            len(
                deduplicate_jobs(
                    [base | {"url": "https://a/1"}, base | {"url": "https://b/2"}]
                )
            ),
            1,
        )
        self.assertEqual(
            len(deduplicate_jobs([base, base | {"location": "Melbourne"}])), 2
        )

    def test_metrics_report_missed_matches_and_unlabeled_predictions(self):
        result = measure(
            [
                dict(
                    query_id="q",
                    labels={"a": True, "b": True, "c": False},
                    shortlist=["a", "c"],
                    predicted_strong=["a", "c", "d"],
                )
            ]
        )[0]
        # Check the expected behavior: metrics report missed matches and unlabeled predictions.
        self.assertEqual(result["observed_recall_at_k"], 0.5)
        self.assertEqual(result["strong_match_precision_on_labeled"], 0.5)
        self.assertEqual(result["missed_labeled_strong"], ["b"])
        self.assertEqual(result["unlabeled_strong_count"], 1)

    def test_hybrid_retrieval_adds_lexical_matches_and_restores_originals(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from langchain_core.documents import Document
        from backend.search.retrieval import retrieve_relevant_jobs

        documents = [
            Document(
                page_content="Python APIs",
                metadata={"url": "a", "original_content": "Full Python job"},
            ),
            Document(
                page_content="C++ robotics",
                metadata={"url": "b", "original_content": "Full robotics job"},
            ),
        ]
        store = MagicMock()
        store._collection.count.return_value = 2
        store.get.return_value = {
            "ids": ["a", "b"],
            "documents": [d.page_content for d in documents],
            "metadatas": [d.metadata for d in documents],
        }
        store.similarity_search.return_value = [documents[0]]
        with patch.dict(
            "sys.modules",
            {
                "langchain_chroma": SimpleNamespace(
                    Chroma=MagicMock(return_value=store)
                ),
                "langchain_openai": SimpleNamespace(OpenAIEmbeddings=MagicMock()),
            },
        ):
            result = retrieve_relevant_jobs("ignored", top_k=0, queries=["C++"])
        # Check the expected behavior: hybrid retrieval adds lexical matches and restores originals.
        self.assertEqual(
            {d.page_content for d in result}, {"Full Python job", "Full robotics job"}
        )
        store.similarity_search.assert_called_once_with("C++", k=2)


class CompareQueryBuildersTests(unittest.TestCase):
    def test_replays_one_run_under_every_builder_without_provider_calls(self):
        import json
        from pathlib import Path
        from unittest.mock import patch
        from langchain_core.documents import Document
        from scripts import compare_query_builders

        with TemporaryDirectory() as directory:
            run = Path(directory) / "run1"
            (run / "vector_db_search_a").mkdir(parents=True)
            profile = {"tech_skills": ["Python"], "work_history": ["Built Python APIs 2025-Present"]}
            (run / "state.json").write_text(
                json.dumps({"profile": profile, "preferences": {"queries": ["Developer"]}})
            )
            jobs = [Document("x", metadata={"title": "Android Developer", "company": "A"}),
                    Document("y", metadata={"title": "Python Developer", "company": "B"})]
            with patch.object(compare_query_builders, "RUNS_DIR", Path(directory)), patch.object(
                compare_query_builders, "retrieve_relevant_jobs", return_value=jobs
            ) as retrieve, patch("backend.search.hyde.job_ads", return_value=["Python Developer ad"]):
                report = compare_query_builders.compare("run1", top=2)
        self.assertEqual(retrieve.call_count, 4)
        self.assertIn("Python", [row["query"] for row in report["legacy"]["queries"]])
        self.assertIn("Job ad: Python Developer ad", [row["query"] for row in report["hyde"]["queries"]])
        self.assertEqual(report["evidence"]["off_target_in_top"]["mobile"], 1)
        self.assertEqual(report["overlap_in_top"], {"legacy": 2, "skills": 2, "hyde": 2})


class RoleWordTests(unittest.TestCase):
    def test_two_letter_role_words_raise_entry_relevance(self):
        from backend.search.ranking import retrieval_query_weights

        ai, web = "Built AI agents 2025-Present", "Built web pages 2025-Present"
        weights = retrieval_query_weights({"work_history": [ai, web]}, ["AI Engineer"])
        self.assertGreater(weights[ai], weights[web])


class RetrievalWeightConfigTests(unittest.TestCase):
    def test_environment_overrides_one_setting_and_rejects_typos(self):
        from unittest.mock import patch
        from backend.search.ranking import retrieval_query_weights, retrieval_weights

        profile = {
            "tech_skills": ["Python"],
            "soft_skills": ["Mentoring"],
            "work_history": ["Mentored Python developers 2025-Present"],
        }
        with patch.dict("os.environ", {"RETRIEVAL_WEIGHTS": '{"votes": {"soft_skills": 1}}'}):
            config = retrieval_weights()
            # Skills, soft skills and experience now hold one vote each.
            self.assertAlmostEqual(retrieval_query_weights(profile, [])["Soft skills: Mentoring"], 1 / 3)
        # Nested keys merge, so the other votes keep their defaults.
        self.assertEqual(config["votes"]["roles"], 0.5)
        for raw in ("not json", "[]", '{"vote": {}}'):
            with patch.dict("os.environ", {"RETRIEVAL_WEIGHTS": raw}):
                with self.assertRaises(ValueError):
                    retrieval_weights()

    def test_seniority_and_filler_words_in_roles_do_not_raise_relevance(self):
        from backend.search.ranking import retrieval_query_weights

        entries = [f"Built thing {n} of the platform 2025-Present" for n in range(4)]
        data = entries + ["Ran data pipelines 2025-Present"]
        weights = retrieval_query_weights({"work_history": data}, ["Senior Head of Data"])
        # "of" is in most entries and "senior"/"head" are seniority words; only "data" counts.
        self.assertGreater(weights[data[-1]], weights[entries[0]])
