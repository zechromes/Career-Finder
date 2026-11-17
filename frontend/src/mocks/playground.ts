// Synthetic playground responses; no resume or job board is contacted.
import { http, HttpResponse } from 'msw'

export const playgroundHandlers = [
  http.post('/api/playground/upload', () =>
    HttpResponse.json({
      profile: {
        name: 'Alex Example',
        headline: 'Data Analyst',
        profile: 'Early-career analyst.',
        career_level: 'junior',
        years_of_experience: 1.5,
        work_history: ['Data Analyst | Example Co | March 2024 – Present'],
        education: ['Bachelor of Computing | Example University | 2023'],
        tech_skills: ['Python', 'SQL', 'Kubernetes'],
        soft_skills: [],
        experience_evidence: [],
        preferred_domains: ['Junior Data Analyst'],
        target_roles_reason: 'Python and SQL work at a junior level.',
        section_headings: ['Experience', 'Education', 'Projects', 'Certifications'],
        sections: [{ heading: 'Projects', entries: ['Job tracker | Personal | Python'] }],
        source_text: 'Synthetic resume text',
      },
      check: {
        source_text_available: true,
        missing_fields: [],
        empty_sections: ['Certifications'],
        entries_checked: 3,
        unsupported_entries: [],
        skills_not_in_resume: ['Kubernetes'],
        years_check: '',
      },
    }),
  ),
  http.post('/api/playground/ingestion', () =>
    HttpResponse.json({
      status: 'Adaptive collection finished: 1 eligible postings; 2/12 search batches',
      messages: [],
      collected: { linkedin: 3 },
      counts: [{ stage: 'filter', reason: 'posted too long ago', board: 'linkedin', count: 2 }],
      jobs: [
        {
          title: 'Junior Data Analyst',
          company: 'Example Co',
          location: 'Sydney NSW',
          board: 'linkedin',
          posted_at: '2026-11-01',
          url: 'https://example.test/job',
          description_chars: 1800,
          description: 'Synthetic posting: Python and SQL reporting.',
        },
      ],
      dropped: [
        {
          title: 'Old Analyst Role',
          company: 'Old Co',
          location: 'Sydney NSW',
          board: 'linkedin',
          stage: 'filter',
          reason: 'posted too long ago',
          url: 'https://example.test/old',
        },
      ],
    }),
  ),
  http.post('/api/playground/retrieval', () =>
    HttpResponse.json({
      queries: [
        { text: 'Junior Data Analyst', weight: 1 },
        { text: 'Python SQL', weight: 1 },
      ],
      ranked: [
        {
          rank: 1,
          title: 'Junior Data Analyst',
          company: 'Example Co',
          location: 'Sydney NSW',
          board: 'linkedin',
          url: 'https://example.test/job',
          above_level: false,
        },
      ],
      total_jobs: 1,
    }),
  ),
]
