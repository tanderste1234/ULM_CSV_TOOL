const addDateBtn = document.getElementById('add-date-btn');
const datesContainer = document.getElementById('dates-container');
const addFieldBtn = document.getElementById('add-field-btn');
const fieldsContainer = document.getElementById('fields-container');
const toolForm = document.getElementById('tool-form');
const statusMessage = document.getElementById('status-message');

// Add dynamic Date input row
addDateBtn.addEventListener('click', () => {
  const dateRow = document.createElement('div');
  dateRow.classList.add('field-row');

  dateRow.innerHTML = `
    <input type="text" name="dynamic-date" placeholder="e.g., 2026-08-29" required>
    <button type="button" class="btn-remove">&times;</button>
  `;

  dateRow.querySelector('.btn-remove').addEventListener('click', () => {
    dateRow.remove();
  });

  datesContainer.appendChild(dateRow);
});

// Add dynamic Field input row
addFieldBtn.addEventListener('click', () => {
  const fieldRow = document.createElement('div');
  fieldRow.classList.add('field-row');

  fieldRow.innerHTML = `
    <input type="text" name="dynamic-field" placeholder="Enter value" required>
    <button type="button" class="btn-remove">&times;</button>
  `;

  // Fixed: Correctly referencing fieldRow instead of dateRow
  fieldRow.querySelector('.btn-remove').addEventListener('click', () => {
    fieldRow.remove();
  });

  fieldsContainer.appendChild(fieldRow);
});

// Submit form payload to Python backend
toolForm.addEventListener('submit', async (e) => {
  e.preventDefault();

  // Single string inputs
  const inputFileName = document.getElementById('input-filename').value;
  const outputFileName = document.getElementById('output-filename').value;
  const dateFieldName = document.getElementById('date-field-name').value;

  // Dynamic array inputs - capturing all matching elements reliably
  const dateInputs = document.querySelectorAll('input[name="dynamic-date"]');
  const fieldInputs = document.querySelectorAll('input[name="dynamic-field"]');
  
  const datesArray = Array.from(dateInputs).map(input => input.value.trim());
  const fieldsArray = Array.from(fieldInputs).map(input => input.value.trim());

  const payload = {
    input_file: inputFileName,
    output_file: outputFileName,
    date_field_name: dateFieldName,
    dates: datesArray,
    fields: fieldsArray
  };

  try {
    statusMessage.style.color = '#2b3674';
    statusMessage.textContent = 'Sending data...';

    const response = await fetch('http://localhost:5000/api/submit', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    if (response.ok) {
      statusMessage.style.color = '#05cd99';
      statusMessage.textContent = 'Success! Data sent to backend.';
    } else {
      statusMessage.style.color = '#ee5d50';
      statusMessage.textContent = `Server error: ${response.status}`;
    }
  } catch (error) {
    statusMessage.style.color = '#ee5d50';
    statusMessage.textContent = 'Failed to connect to backend server.';
  }
});