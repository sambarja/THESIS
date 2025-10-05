import {
  CTable,
  CTableHead,
  CTableRow,
  CTableHeaderCell,
  CTableBody,
  CTableDataCell,
} from "@coreui/react";

    // TODO: replace with API call once backend is ready

function Logs() {
  return (
    <div className="p-4">
      <h2>Dashboard Table</h2>
      <CTable color="dark" striped>
        <CTableHead>
          <CTableRow>
            <CTableHeaderCell scope="col">Truck ID</CTableHeaderCell>
            <CTableHeaderCell scope="col">Date & Time</CTableHeaderCell>
            <CTableHeaderCell scope="col">Event</CTableHeaderCell>
            <CTableHeaderCell scope="col">Status</CTableHeaderCell>
          </CTableRow>
        </CTableHead>
        <CTableBody>
          <CTableRow>
            <CTableHeaderCell scope="row">TRK - 101</CTableHeaderCell>
            <CTableDataCell>2025-10-31 10:00 AM</CTableDataCell>
            <CTableDataCell>Fuel</CTableDataCell>
            <CTableDataCell>Normal</CTableDataCell>
          </CTableRow>
          <CTableRow>
            <CTableHeaderCell scope="row">TRK - 202</CTableHeaderCell>
            <CTableDataCell>2025-04-22 11:00 AM</CTableDataCell>
            <CTableDataCell>Rest</CTableDataCell>
            <CTableDataCell>Alert</CTableDataCell>
          </CTableRow>
          <CTableRow>
            <CTableHeaderCell scope="row">TRK - 303</CTableHeaderCell>
            <CTableDataCell>2025-09-11 07:30 AM</CTableDataCell>
            <CTableDataCell>Maintenance</CTableDataCell>
            <CTableDataCell>Normal</CTableDataCell>
            </CTableRow>
        </CTableBody>
      </CTable>
    </div>
  );
}

export default Logs;
