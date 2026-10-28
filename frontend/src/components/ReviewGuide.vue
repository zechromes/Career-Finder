<script setup lang="ts">
defineProps<{ kind: 'fit' | 'requirements' | 'evidence' }>()
</script>
<template>
  <aside
    class="space-y-3 rounded-xl bg-indigo-50 p-4 text-indigo-950 dark:bg-indigo-950 dark:text-indigo-100"
    :aria-label="`${kind} review help`"
  >
    <template v-if="kind === 'fit'">
      <h3 class="font-semibold">Does this job fit the candidate?</h3>
      <p>
        Compare the candidate profile with the full posting. Make your own judgment before opening
        model answers. You do not need to be a recruiter.
      </p>
      <ul class="list-disc space-y-2 pl-5">
        <li>
          <strong>Strong fit:</strong> the profile supports the mandatory requirements. Missing a
          preferred skill alone does not rule this out.
        </li>
        <li>
          <strong>For review / uncertain:</strong> something important is missing or ambiguous. For
          example, a job requires a licence but the profile says nothing about it.
        </li>
        <li>
          <strong>Not suitable:</strong> there is a clear mismatch. For example, a role requires
          five years of professional experience and the profile explicitly documents only one. Study
          and projects are not employment years.
        </li>
        <li>
          <strong>Unreviewed:</strong> you have not made a decision. This is different from
          reviewing the evidence and deciding it is uncertain.
        </li>
      </ul>
      <p>
        In your explanation, name the requirement and the profile evidence, or say what information
        is missing. Do not assume the candidate lacks a skill just because it is not listed.
      </p>
    </template>
    <template v-else-if="kind === 'requirements'">
      <h3 class="font-semibold">Did the app read the job requirements correctly?</h3>
      <p>
        Check the extracted statement against its posting quote and the full posting. This step is
        about the job, not whether the candidate meets it.
      </p>
      <ul class="list-disc space-y-2 pl-5">
        <li>
          <strong>Correct:</strong> the statement preserves the meaning. “Python or Java” must not
          become “Python and Java.” Mark invented or repeated requirements incorrect.
        </li>
        <li>
          <strong>Mandatory:</strong> explicitly required, such as “must hold a licence.”
          <strong>Preferred:</strong> “desirable,” “a bonus,” or “nice to have.” Choose
          <strong>Unclear</strong> when the wording does not establish importance.
        </li>
        <li>
          <strong>Missing requirement:</strong> a requirement in the posting that is absent from the
          list. Add it and copy its exact posting quote. Benefits are not candidate requirements.
        </li>
      </ul>
      <p>
        Only mark the full-posting check complete after reviewing every shared requirement and
        checking for omissions. You can save a partial review without ticking it.
      </p>
    </template>
    <template v-else>
      <h3 class="font-semibold">Does the model’s explanation follow from the evidence?</h3>
      <p>
        Answer two separate questions for each model assessment: is its reasoning supported, and
        what is your own verdict on this requirement?
      </p>
      <ul class="list-disc space-y-2 pl-5">
        <li>
          <strong>Supported:</strong> the quotes justify the verdict and explanation.
          <strong>Unsupported:</strong> they do not—for example, a Python project is used to claim
          five years of paid Python work. <strong>Uncertain:</strong> you cannot judge the support.
        </li>
        <li>
          <strong>Met:</strong> the profile establishes the requirement.
          <strong>Partially met:</strong> it establishes only part. <strong>Not met:</strong> there
          is evidence of a mismatch. <strong>Unknown:</strong> there is not enough profile evidence.
        </li>
        <li>
          A model saying “Unknown” because the profile never mentions a required licence can be
          <strong>Supported</strong>, with your own verdict also <strong>Unknown</strong>.
        </li>
      </ul>
      <p>
        “Quote found” only means the words occur in the source. It does not prove the model
        interpreted them correctly. Leave items Unreviewed if you have not checked them.
      </p>
    </template>
  </aside>
</template>
