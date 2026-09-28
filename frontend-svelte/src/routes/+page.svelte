<script lang="ts">
  import { Plus, Sun, ChevronDown, Upload, Image as ImageIcon, Package, FileText, Type, Sparkles, Play, Leaf, User } from '@lucide/svelte';
  import { ApiClient } from '$lib/api/client';

  let scriptText = $state('');
  let isGenerating = $state(false);

  function resetForm() {
    scriptText = '';
    isGenerating = false;
  }

  async function handleGenerate() {
    if (!scriptText.trim()) return;
    isGenerating = true;
    try {
      // Logic for generation (currently just a UI skeleton per the prompt)
      // The user wants exactly the UI from the image.
      const response = await ApiClient.analyzeScript(undefined, scriptText);
      console.log(response);
    } catch (e) {
      console.error(e);
    } finally {
      isGenerating = false;
    }
  }
</script>



<main class="page-content">
  <div class="form-header" style="justify-content: space-between;">
    <div style="display: flex; align-items: center; gap: 1rem;">
      <div class="form-header-icon"><Play size={24} fill="currentColor" /></div>
      <div>
        <h2 class="form-title">Create Video Prompts</h2>
        <p class="form-subtitle">Upload your assets and provide the script to generate high-quality video prompts.</p>
      </div>
    </div>
    <button class="btn-new-project" onclick={resetForm}>
      <Plus size={16} /> New Project
    </button>
  </div>

  <div class="steps-grid">
    <!-- Step 1 -->
    <div class="step-container">
      <div class="step-number">1</div>
      <div class="step-content">
        <div class="step-header">
          <div>
            <div class="step-title-row">
              <User size={16} />
              <span class="step-title">Model / Character Photos</span>
              <span class="badge badge-optional">Optional</span>
            </div>
            <p class="step-desc">Upload images of models or characters (multiple images allowed).</p>
          </div>
          <button class="upload-action"><Upload size={14} /> Upload from device</button>
        </div>
        <div class="dropzone">
          <ImageIcon class="dropzone-icon" size={24} />
          <div class="dropzone-text">Drag & drop images here</div>
          <div class="dropzone-subtext">or click to upload (JPG, PNG, WEBP)</div>
        </div>
      </div>
    </div>

    <!-- Step 2 -->
    <div class="step-container">
      <div class="step-number">2</div>
      <div class="step-content">
        <div class="step-header">
          <div>
            <div class="step-title-row">
              <Package size={16} />
              <span class="step-title">Product Photos</span>
              <span class="badge badge-optional">Optional</span>
            </div>
            <p class="step-desc">Upload product images (multiple images allowed).</p>
          </div>
          <button class="upload-action"><Upload size={14} /> Upload from device</button>
        </div>
        <div class="dropzone">
          <ImageIcon class="dropzone-icon" size={24} />
          <div class="dropzone-text">Drag & drop product images here</div>
          <div class="dropzone-subtext">or click to upload (JPG, PNG, WEBP)</div>
        </div>
      </div>
    </div>

    <!-- Step 3 -->
    <div class="step-container">
      <div class="step-number">3</div>
      <div class="step-content">
        <div class="step-header">
          <div>
            <div class="step-title-row">
              <ImageIcon size={16} />
              <span class="step-title">Company Logo</span>
              <span class="badge badge-optional">Optional</span>
            </div>
            <p class="step-desc">Upload your brand logo.</p>
          </div>
          <button class="upload-action"><Upload size={14} /> Upload from device</button>
        </div>
        <div class="dropzone">
          <ImageIcon class="dropzone-icon" size={24} />
          <div class="dropzone-text">Drag & drop logo here</div>
          <div class="dropzone-subtext">or click to upload (JPG, PNG, SVG)</div>
        </div>
      </div>
    </div>

    <!-- Step 4 -->
    <div class="step-container step-full-width">
      <div class="step-number">4</div>
      <div class="step-content">
        <div class="step-header">
          <div>
            <div class="step-title-row">
              <FileText size={16} />
              <span class="step-title">Video Script</span>
              <span class="badge badge-required">Required</span>
            </div>
            <p class="step-desc">Provide your video script. You can upload a file or write directly.</p>
          </div>
          <div style="display: flex; gap: 1rem; align-items: center;">
            <div class="script-tabs">
              <button class="script-tab active"><Type size={14} /> Type Text</button>
              <button class="script-tab"><Upload size={14} /> Upload File</button>
            </div>
            <span class="script-formats">PDF, TXT</span>
          </div>
        </div>
        
        <div style="position: relative;">
          <textarea class="script-textarea" bind:value={scriptText} placeholder="Paste or write your video script here..."></textarea>
          <div class="char-count">{scriptText.length}/5000</div>
        </div>
      </div>
    </div>
  </div>

  <div class="form-footer">
    <button class="btn-generate" onclick={handleGenerate} disabled={isGenerating}>
      <Sparkles size={16} /> Generate Video Prompts →
    </button>
  </div>
</main>
