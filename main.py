import io
import logging
import re

import cv2
import numpy as np
import pandas as pd
import pytesseract as pyt
import streamlit as st
from dateutil import parser
from PIL import Image

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Set Tesseract command path if needed
# pyt.pytesseract.tesseract_cmd = "/usr/bin/tesseract"  # Uncomment and set path if necessary

# Regular expression patterns for extracting fields
transtype_pattern = re.compile(r"^(Transaction Type|Type)\s?:?\s?(.+)")
notes_pattern = re.compile(r"^(Notes|Note|Purpose|Reason)\s?:?\s?(.+)")
transtime_pattern = re.compile(
    r"^(Transaction Time|Date and Time|Date & Time|Transaction Date)\s?:?\s?(.+)"
)
transno_pattern = re.compile(r"^(Transaction No|Transaction ID)\s?:?\s?(.+)")
receiver_pattern = re.compile(r"^(To|Receiver Name|Send To)\s?:?\s?(.+)")
sender_pattern = re.compile(r"^(From|Sender Name|Send From)\s?:?\s?(.+)")
amount_data_pattern = re.compile(r"^(Amount|Total Amount)\s?:?\s?(.+)")


def extract_text_from_image(image):
    """
    Extracts text from an image using Tesseract OCR.

    :param image: Image file
    :return: Extracted text as a string, or None if extraction fails
    """
    try:
        # Convert the image to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Apply a Gaussian blur to reduce noise and smoothen the image
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)

        # Increase contrast using adaptive histogram equalization (CLAHE)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced_img = clahe.apply(blurred)

        # Sharpen the image to make text more readable
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharpened = cv2.filter2D(enhanced_img, -1, kernel)

        # Apply a threshold to convert the image to binary (black and white)
        _, thresh = cv2.threshold(
            sharpened, 200, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        # Convert back to a PIL image
        pil_image = Image.fromarray(thresh)

        # Use Tesseract to do OCR on the image
        config = "--psm 6"
        text = pyt.image_to_string(pil_image, config=config, lang="eng")
        return text

    except Exception as e:
        logging.error(f"Error processing image: {str(e)}")
        return None


def split_text_into_lines(text):
    """
    Splits the extracted text into lines.

    :param text: Extracted text
    :return: List of non-empty lines
    """
    lines = text.split("\n")
    return [line.strip() for line in lines if line.strip()]


def extract_date_time(date_time_str):
    """
    Extracts date and time from the input string using regex and dateutil parser.

    :param date_time_str: String containing date and time
    :return: Formatted date and time
    """
    date_pattern = re.compile(
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2} \w+ \d{4}|\w+ \d{1,2}, \d{4})"
    )
    time_pattern = re.compile(
        r"\b((1[0-2]|0?[1-9]):[0-5][0-9](?::[0-5][0-9])?\s?[APap][Mm]|(2[0-3]|[01]?[0-9]):[0-5][0-9](?::[0-5][0-9])?)\b"
    )

    try:
        date_match = date_pattern.search(date_time_str)
        times_match = time_pattern.search(date_time_str)

        formatted_date = (
            parser.parse(date_match.group()).strftime("%Y/%m/%d") if date_match else ""
        )
        formatted_time = (
            parser.parse(times_match.group()).strftime("%H:%M:%S")
            if times_match
            else ""
        )

    except Exception as e:
        logging.error(f"Error parsing date or time: {e}")
        formatted_date, formatted_time = "", ""

    return formatted_date, formatted_time


def extract_amount_only(amount_str):
    """
    Extracts numeric amount from the amount string using regex.

    :param amount_str: amount with negative sign, MMK, Ks
    :return: numeric amount as a string
    """
    amount_only_pattern = re.compile(r"-?\d*(?:,\d*)*(?:\.\d{2})?")
    amount_pattern_match = amount_only_pattern.search(amount_str)

    return (
        amount_pattern_match.group().replace("-", "").strip()
        if amount_pattern_match
        else amount_str
    )


def extract_transaction_data(text):
    """
    Extracts transaction details from the given text.

    :param text: Text extracted from an image
    :return: Dictionary of extracted transaction details
    """
    transaction_data = {
        "Transaction No": None,
        "Transaction Date": None,
        "Transaction Type": None,
        "Sender Name": None,
        "Amount": None,
        "Receiver Name": None,
        "Notes": None,
    }
    lines = split_text_into_lines(text)
    for line in lines:
        # Transaction Time
        if re.search(transtime_pattern, line):
            transtime_pattern_match = transtime_pattern.search(line)
            date_time_str = transtime_pattern_match.group(2).strip()
            transaction_data["Transaction Date"], _ = extract_date_time(date_time_str)

        # Transaction No
        elif re.search(transno_pattern, line):
            transno_pattern_match = transno_pattern.search(line)
            transaction_data["Transaction No"] = transno_pattern_match.group(2).strip()

        # Transaction Type
        elif re.search(transtype_pattern, line):
            transtype_pattern_match = transtype_pattern.search(line)
            transaction_data["Transaction Type"] = transtype_pattern_match.group(
                2
            ).strip()

        # Amounts
        elif re.search(amount_data_pattern, line):
            amount_data_pattern_match = amount_data_pattern.search(line)
            amount_string = amount_data_pattern_match.group(2).strip()
            transaction_data["Amount"] = extract_amount_only(amount_string)

        # Sender Name
        elif re.search(sender_pattern, line):
            sender_pattern_match = sender_pattern.search(line)
            transaction_data["Sender Name"] = sender_pattern_match.group(2).strip()

        # Receiver Name
        elif re.search(receiver_pattern, line):
            receiver_pattern_match = receiver_pattern.search(line)
            transaction_data["Receiver Name"] = receiver_pattern_match.group(2).strip()

        # Notes
        elif re.search(notes_pattern, line):
            notes_match = notes_pattern.search(line)
            transaction_data["Notes"] = notes_match.group(2).strip()

    return transaction_data


def main():
    st.title("Transaction Details Extractor")

    # Initialize session state for transaction details
    if "all_transaction_details" not in st.session_state:
        st.session_state.all_transaction_details = []

    uploaded_files = st.file_uploader(
        "Upload image files", accept_multiple_files=True, type=["png", "jpg", "jpeg"]
    )

    # Track processed files to avoid duplicates
    processed_files = {
        detail["image_file"] for detail in st.session_state.all_transaction_details
    }

    for uploaded_file in uploaded_files:
        if uploaded_file.name not in processed_files:
            try:
                # Read the image file
                image = Image.open(uploaded_file)
                image_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

                # Extract text from the image
                extracted_text = extract_text_from_image(image_cv)

                if extracted_text:
                    # Extract transaction details using regex
                    transaction_details = extract_transaction_data(extracted_text)
                    transaction_details["image_file"] = uploaded_file.name

                    # Append the extracted details to the session state list
                    st.session_state.all_transaction_details.append(transaction_details)
                else:
                    st.warning(f"Failed to extract text from {uploaded_file.name}")
            except Exception as e:
                st.error(f"Error processing {uploaded_file.name}: {e}")

    # Display all transaction details in a DataFrame with custom column names
    if st.session_state.all_transaction_details:
        df = pd.DataFrame(st.session_state.all_transaction_details)

        # Reorder columns to have 'Amount' at the end
        df = df[
            [
                "Transaction Date",
                "Transaction No",
                "Sender Name",
                "Receiver Name",
                "Notes",
                "image_file",
                "Amount",
            ]
        ]

        # Rename columns for display
        df.columns = [
            "Transaction Date",
            "Transaction Number",
            "Sender",
            "Receiver",
            "Notes",
            "Image File",
            "Amount",
        ]

        # Convert 'Amount' to numeric, handling any non-numeric values
        df["Amount"] = pd.to_numeric(
            df["Amount"].replace(r"[^\d.]", "", regex=True), errors="coerce"
        )

        # Configure the DataFrame display with column_config
        st.dataframe(
            df,
            column_config={
                "Transaction Date": "Date",
                "Transaction Number": "Number",
                "Sender": "From",
                "Receiver": "To",
                "Notes": "Notes",
                "Image File": "File",
                "Amount": st.column_config.NumberColumn(
                    "Amount",
                    help="Transaction amount in currency",
                    format="%.2f",  # Format to two decimal places
                    min_value=0.0,  # Minimum value constraint
                ),
            },
            hide_index=True,
        )

        # Calculate and display the total amount
        total_amount = df["Amount"].sum()
        st.write(f"**Total Amount:** {total_amount}")

        # Export DataFrame to Excel
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Transactions")

        # Provide a download button for the Excel file
        st.download_button(
            label="Download Excel",
            data=excel_buffer,
            file_name="transaction_details.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        st.success("All transaction details have been extracted successfully.")


if __name__ == "__main__":
    main()
