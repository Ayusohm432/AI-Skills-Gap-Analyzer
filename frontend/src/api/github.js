import { secureFetch } from './base';

/**
 * Sends a request to enrich skills from a GitHub profile.
 * 
 * @param {string} githubUsername - The GitHub username to analyze
 * @param {string[]} resumeSkills - Currently known skills to merge with
 * @returns {Promise<Object>} - The enriched analysis response
 */
export const analyzeGithubApi = async (githubUsername, resumeSkills = []) => {
  const response = await secureFetch('/api/v1/analyze/github', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      github_username: githubUsername,
      resume_skills: resumeSkills,
      max_repos: 10
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to analyze GitHub profile');
  }

  return response.json();
};
