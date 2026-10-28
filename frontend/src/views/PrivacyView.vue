<!-- Explain data storage, external provider sharing, and deletion behavior. -->
<!-- Render the accessible interface from the state and handlers above. -->
<template>
  <article class="panel w-full space-y-4">
    <h1 class="text-2xl font-bold">Privacy &amp; data retention</h1>
    <p>
      Your PDF, extracted profile, search preferences and results are stored on this application
      server for 7 days. Expired data is removed on the next server request or restart. Uploading a
      new resume starts a separate run; previous run data remains until it expires.
    </p>
    <p>
      Profiles are saved automatically when a search completes successfully, including searches with
      no matches. You can also save manually. Saved profiles are stored separately on this server
      until you delete them in Saved resumes. New saved resume workspaces contain the original PDF,
      profile text, preferences and job-action flags. Older saved profiles may not have a PDF.
      Deleting a saved profile does not delete earlier searches or uploads, and deleting a search
      does not delete saved profiles. There are no accounts: saved profiles are accessible to anyone
      who can access this application.
    </p>
    <p>
      Successful model assessments can be reused for seven days when the profile, posting, model and
      evaluation instructions are unchanged. These private caches belong to the saved resume or
      temporary run and are removed with it. Cleanup also occurs on cache writes. Saved, dismissed
      and applied flags are synchronized to the saved resume so they carry across its searches.
      Browser storage remains a fallback when synchronization fails. Optional dismissal reasons and
      salary preferences are stored with the owning workspace or saved resume and used to rank
      future shortlists. They are not sent to evaluation models or used to train model weights.
      Restore a job or remove its dismissal preference to stop using that feedback.
    </p>
    <p>
      OpenAI receives resume text to extract your profile and text for job embeddings. Evaluation
      services receive profile text and job text to evaluate fit. Job search services receive search
      terms and filters. Scanned pages are processed locally with Tesseract OCR.
    </p>
    <p>
      Deletion prevents further updates immediately. If a provider request is already running,
      server files are removed after that worker finishes. Cancellation stops further processing but
      keeps results until deletion or expiry. Deleting this server’s files does not revoke requests
      already sent to a provider.
    </p>
    <p>
      Clearing browser storage removes local copies of flags, but not the saved resume’s server
      copy. Delete the saved resume to remove that copy. This version has no accounts: anyone with
      your run URL can access it. Keep it private and run the app on a trusted server.
    </p>
    <p>
      Experiments at /eval send workspace posting and profile text to the selected providers only
      after you start a run. Experiment reports, settings and human labels are kept separately in
      server memory for up to 24 hours (latest 20), cleared on restart, and may remain after a
      source workspace is deleted. Downloaded reports can contain private assessment evidence.
    </p>
    <p>
      Human review datasets keep frozen profile text, job postings, model evidence and reviewer
      labels separately on this server until manually removed from data/evaluation_datasets. They
      survive workspace deletion and server restarts. Downloaded datasets also contain private
      evidence. Creating a snapshot makes no new provider requests.
    </p>
    <p>
      Posting verification means checking that the original posting is still live. This version does
      not perform that check and labels all postings “Not verified”. Fit scores are model
      assessments, not probabilities or guarantees.
    </p>
  </article>
</template>
