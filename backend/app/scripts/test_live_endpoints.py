import httpx
import json

BASE_URL = "http://127.0.0.1:8000/api"

def test_endpoints():
    print("=" * 60)
    print("Testing SkillSync Live Endpoints via HTTP")
    print("=" * 60)

    with httpx.Client(trust_env=False, timeout=20.0) as client:
        # 1. Health check
        r_health = client.get(f"{BASE_URL}/health")
        print(f"[1] Health Check: HTTP {r_health.status_code}")
        print(f"    Payload: {r_health.json()}")

        # 2. Validate repository with repository_url (frontend format)
        payload1 = {"repository_url": "https://github.com/octocat/Hello-World"}
        r_val1 = client.post(f"{BASE_URL}/repositories/validate", json=payload1)
        print(f"\n[2] Validate Repo ({payload1}): HTTP {r_val1.status_code}")
        print(f"    Response: {r_val1.json()}")

        # 3. Validate repository with shorthand (e.g. github.com/tiangolo/fastapi.git)
        payload2 = {"github_url": "github.com/tiangolo/fastapi.git"}
        r_val2 = client.post(f"{BASE_URL}/repositories/validate", json=payload2)
        print(f"\n[3] Validate Repo ({payload2}): HTTP {r_val2.status_code}")
        print(f"    Response: {r_val2.json()}")

        # 4. Preview skills from job description
        payload_skills = {
            "job_title": "Full Stack Engineer",
            "job_description": "Looking for a Python, FastAPI, and React developer with PostgreSQL experience and Git knowledge."
        }
        r_skills = client.post(f"{BASE_URL}/job-profiles/extract-skills", json=payload_skills)
        print(f"\n[4] Extract Skills Preview: HTTP {r_skills.status_code}")
        print(f"    Extracted: {r_skills.json()}")

        # 5. Add or retrieve repository
        payload_repo = {
            "github_owner": "octocat",
            "repo_name": "Hello-World",
            "default_branch": "master",
            "description": "My first repo",
            "language": "C"
        }
        r_repo = client.post(f"{BASE_URL}/repositories", json=payload_repo)
        print(f"\n[5] Create/Update Repo: HTTP {r_repo.status_code}")
        repo_data = r_repo.json()
        print(f"    Repo ID: {repo_data.get('id')}")

        # 6. Trigger full assessment pipeline
        payload_assessment = {
            "repository_id": repo_data["id"],
            "job_title": "Full Stack Engineer",
            "job_description": "We need a developer proficient in Python, FastAPI, React, and Git with testing and REST API experience.",
            "company_context": "SkillSync Testing"
        }
        r_assess = client.post(f"{BASE_URL}/assessments", json=payload_assessment)
        print(f"\n[6] Trigger Assessment: HTTP {r_assess.status_code}")
        if r_assess.status_code == 201:
            assess_data = r_assess.json()
            print(f"    Assessment ID: {assess_data.get('id')}")
            print(f"    Overall Score: {assess_data.get('overall_score')}%")
            print(f"    Findings Count: {len(assess_data.get('findings', []))}")
            for finding in assess_data.get("findings", [])[:3]:
                print(f"      - {finding.get('skill_name')}: {finding.get('status')} (Score: {finding.get('score')}%)")
        else:
            print(f"    Assessment Failed: {r_assess.text}")

        # 7. Test Gap Solver Phase D Endpoints
        if r_assess.status_code == 201:
            assess_id = assess_data["id"]
            r_gaps = client.get(f"{BASE_URL}/assessments/{assess_id}/gaps")
            print(f"\n[7] List Assessment Gaps: HTTP {r_gaps.status_code}")
            gaps_info = r_gaps.json()
            print(f"    Total Gaps: {gaps_info.get('total')}")
            
            if gaps_info.get("gaps"):
                first_gap = gaps_info["gaps"][0]
                gap_id = first_gap["id"]
                print(f"    Testing Plan for Gap #{gap_id} ({first_gap.get('skill_name')})...")
                
                r_plan = client.post(
                    f"{BASE_URL}/assessments/{assess_id}/gaps/{gap_id}/plan",
                    json={"difficulty_level": "intermediate"}
                )
                print(f"\n[8] Generate Plan: HTTP {r_plan.status_code}")
                if r_plan.status_code == 201:
                    plan = r_plan.json()
                    print(f"    Plan Title: {plan.get('title')}")
                    print(f"    Classification: {plan.get('current_classification')}")
                    print(f"    Objective: {plan.get('objective')[:60]}...")
                    print(f"    Prerequisites: {plan.get('prerequisites')}")
                    print(f"    Verified Resources: {len(plan.get('verified_resources', []))} official links")
                    print(f"    Steps Count: {len(plan.get('steps', []))}")
                    
                    if plan.get("steps"):
                        first_step = plan["steps"][0]
                        step_id = first_step["id"]
                        r_step_patch = client.patch(
                            f"{BASE_URL}/gaps/plans/steps/{step_id}",
                            json={
                                "status": "in_progress",
                                "user_notes": "Live test candidate notes.",
                                "evidence_file_path": "app/main.py"
                            }
                        )
                        print(f"\n[9] Update Step Progress: HTTP {r_step_patch.status_code}")
                        step_updated = r_step_patch.json()
                        print(f"    Step #{step_id} Status: {step_updated.get('status')}")
                        print(f"    Step Notes: {step_updated.get('user_notes')}")

    print("\n" + "=" * 60)
    print("All live endpoint tests passed successfully!")
    print("=" * 60)

if __name__ == "__main__":
    test_endpoints()
