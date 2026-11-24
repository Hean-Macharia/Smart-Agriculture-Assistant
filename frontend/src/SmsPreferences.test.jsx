import {afterEach,describe,expect,it,vi} from "vitest";
import {cleanup,render,screen,waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SmsPreferences from "./SmsPreferences.jsx";
import {api} from "./api.js";

vi.mock("./api.js",()=>({api:vi.fn()}));

const initial={phone_number:"+254712345678",consented:false,consented_at:null,opted_out_at:null,language:"en",categories:[],phone_verified:false,consent_history:[]};

describe("SMS preferences",()=>{
 afterEach(()=>cleanup());
 it("loads preferences, selects language/categories, then posts explicit consent",async()=>{
  api.mockResolvedValueOnce(initial).mockResolvedValueOnce({...initial,consented:true,language:"sw",categories:["WEATHER_ALERT"]});
  const user=userEvent.setup();
  render(<SmsPreferences/>);
  expect(await screen.findByText(/not verified/i)).toBeTruthy();
  await user.selectOptions(screen.getByLabelText(/Message language/i),"sw");
  await user.click(screen.getByLabelText(/Weather alerts/i));
  await user.click(screen.getByRole("button",{name:/Give consent and save/i}));
  await waitFor(()=>expect(api).toHaveBeenLastCalledWith("/notifications/preferences",expect.objectContaining({method:"PUT"})));
  const posted=JSON.parse(api.mock.calls[1][1].body);
  expect(posted).toEqual({consented:true,language:"sw",categories:["WEATHER_ALERT"]});
  expect(await screen.findByText(/from this phone to the service number/i)).toBeTruthy();
 });

 it("shows API errors and provides an opt-out control",async()=>{
  api.mockResolvedValueOnce(initial).mockRejectedValueOnce(new Error("Could not save preferences"));
  render(<SmsPreferences/>);
  const user=userEvent.setup();
  await screen.findByText(/SMS information/i);
  await user.click(screen.getByRole("button",{name:/Turn SMS off/i}));
  expect((await screen.findByRole("alert")).textContent).toContain("Could not save preferences");
 });

 it("keeps loading feedback while preferences are fetched",()=>{
  api.mockReturnValueOnce(new Promise(()=>{}));
  render(<SmsPreferences/>);
  expect(screen.getByRole("status").textContent).toContain("Loading SMS preferences");
 });
});
